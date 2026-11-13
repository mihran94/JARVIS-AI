package com.jarvisblue.core.security

import android.util.Base64
import java.security.SecureRandom

/**
 * Encrypts/decrypts short byte payloads with AES-256-GCM.
 *
 * Wire format (all Base64, separated by '.'):
 *   v1.<iv>.<ciphertext>.<tag>
 */
class CipherBox(private val keyManager: KeystoreKeyManager = KeystoreKeyManager()) {

    fun encrypt(plain: ByteArray): String {
        val iv = keyManager.newInitVector()
        val cipher = keyManager.cipherForEncryption(iv)
        val combined = cipher.doFinal(plain)
        val cipherText = combined.copyOfRange(0, combined.size - TAG_LENGTH)
        val tag = combined.copyOfRange(combined.size - TAG_LENGTH, combined.size)
        return listOf(
            VERSION,
            Base64.encodeToString(iv, Base64.NO_WRAP),
            Base64.encodeToString(cipherText, Base64.NO_WRAP),
            Base64.encodeToString(tag, Base64.NO_WRAP),
        ).joinToString(".")
    }

    fun decrypt(payload: String): ByteArray {
        val parts = payload.split(".")
        require(parts.size == 4 && parts[0] == VERSION) { "Unsupported ciphertext envelope" }
        val iv = Base64.decode(parts[1], Base64.NO_WRAP)
        val cipherText = Base64.decode(parts[2], Base64.NO_WRAP)
        val tag = Base64.decode(parts[3], Base64.NO_WRAP)
        val cipher = keyManager.cipherForDecryption(iv)
        return cipher.doFinal(cipherText + tag)
    }

    fun encrypt(text: String): String = encrypt(text.toByteArray(Charsets.UTF_8))

    fun decryptToString(payload: String): String = decrypt(payload).toString(Charsets.UTF_8)

    companion object {
        private const val VERSION = "v1"
        private const val TAG_LENGTH = 16

        fun randomBytes(count: Int): ByteArray = ByteArray(count).also { SecureRandom().nextBytes(it) }
    }
}
