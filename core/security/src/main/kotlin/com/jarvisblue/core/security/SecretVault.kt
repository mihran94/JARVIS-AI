package com.jarvisblue.core.security

import android.content.Context
import androidx.core.content.edit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.concurrent.ConcurrentHashMap

/**
 * Stores provider API keys and pairing secrets.
 *
 * Values are encrypted with the Keystore master key before they touch disk, so a
 * rooted file-system dump of the app's data directory yields ciphertext only.
 * The plaintext is held in memory only for as long as a request needs it.
 */
class SecretVault(
    private val context: Context,
    private val cipherBox: CipherBox = CipherBox(),
) {

    private val cache = ConcurrentHashMap<String, String>()

    private val prefs get() = context.getSharedPreferences(FILE_NAME, Context.MODE_PRIVATE)

    suspend fun put(alias: String, secret: String) = withContext(Dispatchers.IO) {
        val encrypted = cipherBox.encrypt(secret)
        prefs.edit { putString(key(alias), encrypted) }
        cache[alias] = secret
    }

    suspend fun get(alias: String): String? = withContext(Dispatchers.IO) {
        cache[alias] ?: runCatching {
            val raw = prefs.getString(key(alias), null) ?: return@runCatching null
            cipherBox.decryptToString(raw).also { cache[alias] = it }
        }.getOrNull()
    }

    suspend fun has(alias: String): Boolean = get(alias) != null

    suspend fun remove(alias: String) = withContext(Dispatchers.IO) {
        prefs.edit { remove(key(alias)) }
        cache.remove(alias)
    }

    suspend fun clear() = withContext(Dispatchers.IO) {
        prefs.edit { clear() }
        cache.clear()
    }

    /** Returns only the last four characters so the UI can show a secret without leaking it. */
    suspend fun masked(alias: String): String? = get(alias)?.let { com.jarvisblue.core.common.Redactor.mask(it) }

    private fun key(alias: String) = "secret_$alias"

    companion object {
        const val FILE_NAME = "jarvis_blue_secrets"
        const val ALIAS_OPENAI = "openai_api_key"
        const val ALIAS_GEMINI = "gemini_api_key"
        const val ALIAS_MINIMAX = "minimax_api_key"
        const val ALIAS_OLLAMA = "ollama_api_key"
        const val ALIAS_WINDOWS_PEER = "windows_peer_secret"
    }
}
