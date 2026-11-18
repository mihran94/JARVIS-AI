package com.jarvisblue.core.common

/**
 * The pairing code the desktop shows and the phone reads.
 *
 * The code is a short text block:
 *
 *     JARVIS-BRIDGE-v1
 *     bridge=https://pc.example.lan:8765
 *     key=jarvis-iphone-v1
 *     secret=<the one time secret>
 *     expires=1764000000
 *     fp=<the SHA-256 of the server certificate>
 *
 * The owner can paste the whole code, and the address, the secret and the
 * fingerprint of the certificate all come with it. The secret can also be
 * pasted on its own, which is what the older versions of the app did, and
 * then there is no fingerprint and no pinning.
 *
 * WHAT THIS WILL NOT DO
 * * It never repairs a damaged fingerprint. A code that was tampered with
 *   is not used, and the owner is told that it was not used.
 * * It never accepts a secret that is too short to be one.
 */
data class PairingDetails(
    /** The shared secret, which is at least 32 characters long. */
    val secret: String,
    /** The address the desktop is reached on, when the code carries one. */
    val host: String = "",
    /** The port, when the code carries one. */
    val port: Int = 0,
    /** The SHA-256 of the certificate, when the code carries one. */
    val fingerprint: String? = null,
    /** When the code stops being usable, in whole seconds. */
    val expiresAt: Long = 0,
    /** True when the input was a pairing code and not a bare secret. */
    val wasPairingCode: Boolean = false,
) {
    /**
     * The address to use: what the owner typed, or the one the pairing
     * code carries when the field was left empty.
     */
    fun mergeHost(typed: String): String = typed.trim().ifEmpty { host }

    /**
     * The port to use: what the owner typed, or the one the pairing code
     * carries when the field was left empty.
     */
    fun mergePort(typed: String): String {
        val entered = typed.trim()
        if (entered.isNotEmpty()) return entered
        return if (port > 0) port.toString() else ""
    }
}

object PairingCode {

    /** The first line of every pairing code. */
    const val FORMAT = "JARVIS-BRIDGE-v1"

    /** The shortest secret the bridge accepts. */
    const val MINIMUM_SECRET_LENGTH = 32

    /**
     * Read what the owner pasted.
     *
     * A whole pairing code gives the address, the secret, the
     * fingerprint and the expiry. A bare secret gives only the secret.
     */
    fun parse(text: String?): PairingDetails {
        val value = (text ?: "").trim()
        if (value.isEmpty()) {
            throw IllegalArgumentException("Enter the pairing code or its secret")
        }
        // The code starts with the format marker. It is looked for at the
        // start of the text and not on a line of its own, because the
        // field the owner pastes into takes one line.
        val isCode = value.startsWith(FORMAT, ignoreCase = true)
        if (!isCode) {
            // The owner pasted the secret on its own. There is no address
            // and no certificate to pin, and that is said plainly rather
            // than guessed at.
            if (value.length < MINIMUM_SECRET_LENGTH) {
                throw IllegalArgumentException(
                    "The pairing secret needs at least $MINIMUM_SECRET_LENGTH characters"
                )
            }
            return PairingDetails(secret = value)
        }
        // The fields are found wherever they are, so the code is read the
        // same whether the owner pasted it as it was shown, with one field
        // on each line, or as a single line because the field they pasted
        // it into takes one line only.
        val fields = mutableMapOf<String, String>()
        for (key in listOf("bridge", "key", "secret", "expires", "fp")) {
            val found = Regex("(?:^|\\s)$key=(\\S*)").find(value)
            if (found != null && key !in fields) fields[key] = found.groupValues[1].trim()
        }
        val secret = fields["secret"].orEmpty()
        if (secret.length < MINIMUM_SECRET_LENGTH) {
            throw IllegalArgumentException(
                "The pairing code carries no usable secret"
            )
        }
        var host = ""
        var port = 0
        fields["bridge"]?.let { bridge ->
            val withoutScheme = bridge.substringAfter("://", bridge)
            val authority = withoutScheme.substringBefore('/')
            host = authority.substringBefore(':')
            val portText = authority.substringAfter(':', "")
            port = portText.toIntOrNull() ?: 0
        }
        val rawFingerprint = fields["fp"]
        val fingerprint = if (rawFingerprint != null && CertificatePin.isFingerprint(rawFingerprint)) {
            rawFingerprint.lowercase()
        } else {
            null
        }
        return PairingDetails(
            secret = secret,
            host = host,
            port = port,
            fingerprint = fingerprint,
            expiresAt = fields["expires"]?.toLongOrNull() ?: 0,
            wasPairingCode = true,
        )
    }
}
