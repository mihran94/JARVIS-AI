package com.jarvisblue.core.security

import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyInfo
import android.security.keystore.KeyProperties
import android.security.keystore.StrongBoxUnavailableException
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.PBEKeySpec

/**
 * Owns the hardware-backed AES key that protects everything the app stores.
 *
 * The key never leaves the Android Keystore; only ciphertext is written to disk.
 * StrongBox (dedicated secure element) is requested when the device provides it
 * and gracefully downgraded to the TEE/software-backed keystore otherwise.
 */
class KeystoreKeyManager(
    private val alias: String = DEFAULT_ALIAS,
    private val requireUserAuthentication: Boolean = false,
) {

    private val keyStore: KeyStore by lazy {
        KeyStore.getInstance(KEYSTORE_PROVIDER).apply { load(null) }
    }

    /** True when the secret key is backed by a hardware secure element (TEE or StrongBox). */
    val isHardwareBacked: Boolean
        get() {
            val key = runCatching { keyStore.getKey(alias, null) as? SecretKey }.getOrNull()
                ?: return false
            val info = runCatching {
                SecretKeyFactory.getInstance(key.algorithm, KEYSTORE_PROVIDER)
                    .getKeySpec(key, KeyInfo::class.java) as? KeyInfo
            }.getOrNull() ?: return false
            return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                info.securityLevel != KeyProperties.SECURITY_LEVEL_SOFTWARE
            } else {
                @Suppress("DEPRECATION")
                info.isInsideSecureHardware
            }
        }

    fun getOrCreateKey(): SecretKey {
        (keyStore.getEntry(alias, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        return generateKey()
    }

    private fun generateKey(): SecretKey {
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE_PROVIDER)
        val spec = buildSpec(alias, requireUserAuthentication)
        return try {
            generator.init(spec)
            generator.generateKey()
        } catch (e: StrongBoxUnavailableException) {
            // No StrongBox on this device: fall back to the regular AndroidKeyStore provider.
            generator.init(buildSpec(alias, requireUserAuthentication, strongBox = false))
            generator.generateKey()
        }
    }

    private fun buildSpec(
        keyAlias: String,
        userAuth: Boolean,
        strongBox: Boolean = true,
    ): KeyGenParameterSpec {
        val builder = KeyGenParameterSpec.Builder(
            keyAlias,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(KEY_SIZE_BITS)
            .setRandomizedEncryptionRequired(true)
            .setUserAuthenticationRequired(userAuth)

        if (userAuth && Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            // 30-second validity window so the user is not prompted for every single call.
            builder.setUserAuthenticationParameters(30, KeyProperties.AUTH_BIOMETRIC_STRONG)
        }
        if (strongBox && Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            builder.setIsStrongBoxBacked(true)
        }
        return builder.build()
    }

    fun newInitVector(): ByteArray =
        ByteArray(GCM_IV_LENGTH).also { java.security.SecureRandom().nextBytes(it) }

    /**
     * Android Keystore with randomized encryption MUST generate the GCM IV.
     * Passing a caller-provided IV crashes on Android 12+; callers serialize
     * cipher.iv with their ciphertext for authenticated decryption.
     */
    fun cipherForEncryption(): Cipher =
        Cipher.getInstance(TRANSFORMATION).apply {
            init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        }

    fun cipherForDecryption(iv: ByteArray): Cipher =
        Cipher.getInstance(TRANSFORMATION).apply {
            init(Cipher.DECRYPT_MODE, getOrCreateKey(), GCMParameterSpec(GCM_TAG_BITS, iv))
        }

    fun deleteKey() {
        runCatching { keyStore.deleteEntry(alias) }
    }

    companion object {
        const val DEFAULT_ALIAS = "jarvis_blue_master_key_v1"
        const val KEYSTORE_PROVIDER = "AndroidKeyStore"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val GCM_IV_LENGTH = 12
        const val GCM_TAG_BITS = 128
        const val KEY_SIZE_BITS = 256
    }
}

/** Derives a key from a passphrase using PBKDF2 — used for user-supplied vault passphrases. */
object Pbkdf2 {
    fun derive(
        passphrase: CharArray,
        salt: ByteArray,
        iterations: Int = 120_000,
        length: Int = 256,
    ): ByteArray {
        val spec = PBEKeySpec(passphrase, salt, iterations, length)
        return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
            .generateSecret(spec)
            .encoded
    }
}
