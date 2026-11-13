package com.jarvisblue.core.ai

import com.jarvisblue.core.database.ProviderConfigRepository
import com.jarvisblue.core.model.ProviderId
import com.jarvisblue.core.security.SecretVault
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import kotlinx.coroutines.flow.first
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Builds the effective provider settings by combining the persisted
 * (non-secret) configuration with the Keystore-encrypted API key.
 */
class ProviderSettingsResolver @Inject constructor(
    private val secretVault: SecretVault,
    private val configRepository: ProviderConfigRepository,
) {
    suspend fun settingsFor(providerId: ProviderId): ProviderSettings {
        val config = configRepository.observeAll().first().firstOrNull { it.providerId == providerId }
        val keyAlias = when (providerId) {
            ProviderId.OPENAI -> SecretVault.ALIAS_OPENAI
            ProviderId.GEMINI -> SecretVault.ALIAS_GEMINI
            ProviderId.MINIMAX -> SecretVault.ALIAS_MINIMAX
            ProviderId.OLLAMA -> SecretVault.ALIAS_OLLAMA
            ProviderId.OPENAI_COMPATIBLE -> SecretVault.ALIAS_OLLAMA
            ProviderId.OFFLINE_ECHO -> null
        }
        return ProviderSettings(
            baseUrl = config?.baseUrl,
            apiKey = keyAlias?.let { secretVault.get(it) },
            defaultModelId = config?.defaultModelId,
            temperature = config?.temperature ?: 0.3,
            maxOutputTokens = config?.maxOutputTokens ?: 2048,
        )
    }
}

@Module
@InstallIn(SingletonComponent::class)
object AiModule {

    @Provides
    @Singleton
    fun provideHttpClient(): AiHttpClient = AiHttpClient()

    @Provides
    @Singleton
    fun provideOpenAiProvider(client: AiHttpClient): OpenAiProvider = OpenAiProvider(client)

    @Provides
    @Singleton
    fun provideGeminiProvider(client: AiHttpClient): GeminiProvider = GeminiProvider(client)

    @Provides
    @Singleton
    fun provideMiniMaxProvider(client: AiHttpClient): MiniMaxProvider = MiniMaxProvider(client)

    @Provides
    @Singleton
    fun provideOllamaProvider(client: AiHttpClient): OllamaProvider = OllamaProvider(client)

    @Provides
    @Singleton
    fun provideGenericProvider(client: AiHttpClient): GenericOpenAiProvider = GenericOpenAiProvider(client)

    @Provides
    @Singleton
    fun provideProviderRegistry(
        openAi: OpenAiProvider,
        gemini: GeminiProvider,
        miniMax: MiniMaxProvider,
        ollama: OllamaProvider,
        generic: GenericOpenAiProvider,
    ): ProviderRegistry = ProviderRegistry(
        mapOf(
            ProviderId.OPENAI to openAi,
            ProviderId.GEMINI to gemini,
            ProviderId.MINIMAX to miniMax,
            ProviderId.OLLAMA to ollama,
            ProviderId.OPENAI_COMPATIBLE to generic,
        ),
    )

    @Provides
    @Singleton
    fun provideTokenBudgetTracker(): TokenBudgetTracker = TokenBudgetTracker()

    @Provides
    @Singleton
    fun provideAiRouter(
        registry: ProviderRegistry,
        resolver: ProviderSettingsResolver,
        budgetTracker: TokenBudgetTracker,
    ): AiRouter = AiRouter(
        registry = registry,
        settingsProvider = { resolver.settingsFor(it) },
        budgetTracker = budgetTracker,
    )
}
