package com.jarvisblue.core.security

import android.content.Context
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object SecurityModule {

    @Provides
    @Singleton
    fun provideKeystoreKeyManager(): KeystoreKeyManager = KeystoreKeyManager()

    @Provides
    @Singleton
    fun provideCipherBox(keyManager: KeystoreKeyManager): CipherBox = CipherBox(keyManager)

    @Provides
    @Singleton
    fun provideSecretVault(
        @ApplicationContext context: Context,
        cipherBox: CipherBox,
    ): SecretVault = SecretVault(context, cipherBox)

    @Provides
    @Singleton
    fun providePermissionGrantStore(
        @ApplicationContext context: Context,
        cipherBox: CipherBox,
    ): PermissionGrantStore = PermissionGrantStore(context, cipherBox)

    @Provides
    @Singleton
    fun provideBiometricGate(@ApplicationContext context: Context): BiometricGate = BiometricGate(context)

    @Provides
    @Singleton
    fun provideAppLockController(@ApplicationContext context: Context): AppLockController =
        AppLockController(context)

    @Provides
    @Singleton
    fun provideEmergencyStop(@ApplicationContext context: Context): EmergencyStop =
        EmergencyStop(context)
}
