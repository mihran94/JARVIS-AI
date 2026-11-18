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
    fun provideBridgeClient(secretVault: SecretVault): BridgeClient {
        return BridgeClient(
            // The certificate the bridge was paired with is read from the
            // vault when the client is first needed. When it is known, the
            // connection accepts that one certificate and no other. When
            // it is not known, the system trust store is used, and the
            // owner is told so rather than being given a false assurance.
            httpClientFactory = {
                val fingerprint = secretVault.get(SecretVault.ALIAS_WINDOWS_PEER_CERT)
                BridgeClient.defaultClient(fingerprint)
            },
            secretProvider = { secretVault.get(SecretVault.ALIAS_WINDOWS_PEER) },
        )
    }
}
