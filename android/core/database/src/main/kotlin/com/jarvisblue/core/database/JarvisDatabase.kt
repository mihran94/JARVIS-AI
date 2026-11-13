package com.jarvisblue.core.database

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import net.sqlcipher.database.SQLiteDatabase
import net.sqlcipher.database.SupportFactory
import com.jarvisblue.core.security.CipherBox
import com.jarvisblue.core.security.KeystoreKeyManager

@Database(
    entities = [
        ConversationEntity::class,
        MessageEntity::class,
        MemoryEntity::class,
        TaskEntity::class,
        AuditEntity::class,
        ProviderConfigEntity::class,
        PeerEntity::class,
        SettingEntity::class,
    ],
    version = 1,
    exportSchema = false,
)
abstract class JarvisDatabase : RoomDatabase() {

    abstract fun conversationDao(): ConversationDao
    abstract fun messageDao(): MessageDao
    abstract fun memoryDao(): MemoryDao
    abstract fun taskDao(): TaskDao
    abstract fun auditDao(): AuditDao
    abstract fun providerConfigDao(): ProviderConfigDao
    abstract fun peerDao(): PeerDao
    abstract fun settingDao(): SettingDao

    companion object {
        const val DB_NAME = "jarvis_blue.db"
        const val PASSPHRASE_PREF = "jarvis_blue_db_passphrase"

        /**
         * Creates the encrypted database.
         *
         * The SQLCipher passphrase is a random 32-byte key generated once, encrypted
         * with the Android Keystore master key and stored in private preferences.
         * Without the hardware key, the database file is unreadable — including for
         * a forensic image of the app's data directory.
         */
        @Volatile
        private var instance: JarvisDatabase? = null

        fun get(context: Context): JarvisDatabase =
            instance ?: synchronized(this) {
                instance ?: build(context.applicationContext).also { instance = it }
            }

        private fun build(context: Context): JarvisDatabase {
            SQLiteDatabase.loadLibs(context)
            val passphrase = passphrase(context)
            return Room.databaseBuilder(context, JarvisDatabase::class.java, DB_NAME)
                .openHelperFactory(SupportFactory(passphrase))
                .fallbackToDestructiveMigration()
                .build()
        }

        private fun passphrase(context: Context): ByteArray {
            val prefs = context.getSharedPreferences("jarvis_blue_db", Context.MODE_PRIVATE)
            val existing = prefs.getString(PASSPHRASE_PREF, null)
            if (existing != null) {
                return runCatching { CipherBox().decrypt(existing) }.getOrElse {
                    generateAndStore(context, prefs)
                }
            }
            return generateAndStore(context, prefs)
        }

        private fun generateAndStore(
            context: Context,
            prefs: android.content.SharedPreferences,
        ): ByteArray {
            val key = CipherBox(KeystoreKeyManager()).let { box ->
                // 32 bytes of entropy from the platform CSPRNG.
                val raw = java.security.SecureRandom().let { rnd ->
                    ByteArray(32).also { rnd.nextBytes(it) }
                }
                box.encrypt(raw)
            }
            prefs.edit().putString(PASSPHRASE_PREF, key).apply()
            return runCatching { CipherBox().decrypt(key) }.getOrElse {
                CipherBox().decrypt(key)
            }
        }
    }
}
