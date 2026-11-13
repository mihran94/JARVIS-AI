package com.jarvisblue.core.windows

import com.jarvisblue.core.security.SecretVault
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object WindowsModule {

    @Provides
    @Singleton
    fun provideBridgeClient(secretVault: SecretVault): BridgeClient = BridgeClient(
        secretProvider = { secretVault.get(SecretVault.ALIAS_WINDOWS_PEER) },
    )
}
