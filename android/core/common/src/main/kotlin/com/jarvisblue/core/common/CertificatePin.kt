package com.jarvisblue.core.common

import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.Base64
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/**
 * Pinning the certificate of the Windows bridge.
 *
 * WHY THE PHONE PINS A CERTIFICATE
 * The desktop makes its own certificate for the private listener. Nobody
 * signs it, and nobody's authority list knows it. The phone therefore
 * cannot ask "is this certificate trusted?" the usual way, because the
 * answer is always no.
 *
 * So the pairing code carries the fingerprint of that one certificate:
 * the SHA-256 of its DER form, in sixty-four hexadecimal characters. The
 * phone pins it, and from then on it accepts that certificate and no
 * other. A different certificate on the same address is refused, and so
 * is a connection to a different address.
 *
 * WHY THE HOST NAME IS NOT CHECKED
 * The certificate is for the bridge, not for the address the owner typed:
 * its subject is `CN=JARVIS AI bridge`, and the owner reaches the
 * computer by whatever name their network gives it. The host name check
 * is therefore replaced by the pin. That is safe because the pin is
 * stronger: it names one certificate exactly, while the host name only
 * names one of many a certificate could be issued for.
 *
 * WHAT THIS MODULE WILL NOT DO
 * * It never falls back to the system trust store. A certificate that is
 *   not the pinned one is refused, even one that is perfectly valid and
 *   signed by a public authority. That is the point of pinning.
 * * It never accepts a certificate because its name matched. Only the
 *   pinned certificate is accepted.
 */
object CertificatePin {

    /** How many hexadecimal characters a SHA-256 fingerprint has. */
    private const val FINGERPRINT_LENGTH = 64

    /**
     * True when the text is a SHA-256 fingerprint: sixty-four lowercase
     * hexadecimal characters.
     */
    fun isFingerprint(text: String?): Boolean {
        val value = text?.trim()?.lowercase() ?: return false
        if (value.length != FINGERPRINT_LENGTH) return false
        return value.all { it in '0'..'9' || it in 'a'..'f' }
    }

    /**
     * The fingerprint in the form the pin libraries use: `sha256/<base64>`.
     *
     * The pairing code carries the fingerprint in hexadecimal, because that
     * is what a person can read out and compare. The pin libraries want
     * the same digest in base64, so it is converted here rather than
     * being asked of the owner.
     */
    fun pinOf(fingerprint: String): String {
        require(isFingerprint(fingerprint)) {
            "A certificate fingerprint is $FINGERPRINT_LENGTH hexadecimal characters."
        }
        val digest = fingerprint.trim().lowercase().chunked(2)
            .map { it.toInt(16).toByte() }.toByteArray()
        return "sha256/" + Base64.getEncoder().encodeToString(digest)
    }

    /**
     * The fingerprint a pairing code carries, or null when it carries none
     * or carries one that is damaged.
     *
     * A damaged fingerprint is not used and is not repaired. A code that
     * was tampered with must not be quietly accepted.
     */
    fun fingerprintFromPairingCode(text: String?): String? {
        val code = text ?: return null
        val line = code.lines()
            .map { it.trim() }
            .firstOrNull { it.startsWith("fp=", ignoreCase = true) }
            ?: return null
        val value = line.substringAfter('=').trim().lowercase()
        return if (isFingerprint(value)) value else null
    }

    /**
     * A trust manager that trusts exactly the pinned certificate.
     *
     * The comparison is made on the SHA-256 of the certificate the server
     * presented, and it is made in constant time, so a wrong certificate
     * is refused and the answer leaks nothing about how wrong it was.
     */
    fun trustManagerFor(fingerprint: String): X509TrustManager {
        require(isFingerprint(fingerprint)) {
            "A certificate fingerprint is $FINGERPRINT_LENGTH hexadecimal characters."
        }
        val expected = fingerprint.trim().lowercase().chunked(2)
            .map { it.toInt(16).toByte() }.toByteArray()
        return object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<out X509Certificate>, authType: String) {
                throw CertificateException("This bridge is not a server that asks for a client certificate.")
            }

            override fun checkServerTrusted(chain: Array<out X509Certificate>, authType: String) {
                val leaf = chain.firstOrNull()
                    ?: throw CertificateException("The server sent no certificate.")
                val digest = MessageDigest.getInstance("SHA-256").digest(leaf.encoded)
                if (!MessageDigest.isEqual(digest, expected)) {
                    throw CertificateException(
                        "The certificate is not the one that was pinned. " +
                            "The pairing code and the certificate do not belong together."
                    )
                }
            }

            override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
        }
    }

    /**
     * The host name check for a pinned connection.
     *
     * The identity of the peer is the pinned certificate, not the name
     * the owner typed, so the name is not checked. The trust manager is
     * what decides, and it accepts one certificate and no other.
     */
    fun hostnameVerifier(): HostnameVerifier = HostnameVerifier { _, _ -> true }

    /**
     * The TLS context that trusts the pinned certificate and nothing else.
     */
    fun sslContextFor(fingerprint: String): SSLContext {
        val manager = trustManagerFor(fingerprint)
        val context = SSLContext.getInstance("TLS")
        context.init(null, arrayOf<TrustManager>(manager), java.security.SecureRandom())
        return context
    }
}
