package com.jarvisblue.core.voice

import android.content.Context
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object VoiceModule {

    @Provides
    @Singleton
    fun provideSpeechRecognizerController(
        @ApplicationContext context: Context,
    ): SpeechRecognizerController = SpeechRecognizerController(context)

    @Provides
    @Singleton
    fun provideTextToSpeechController(
        @ApplicationContext context: Context,
    ): TextToSpeechController = TextToSpeechController(context)

    @Provides
    @Singleton
    fun provideWakePhraseMatcher(): WakePhraseMatcher = WakePhraseMatcher()

    @Provides
    @Singleton
    fun provideWakeWordEngine(
        recognizer: SpeechRecognizerController,
        matcher: WakePhraseMatcher,
    ): WakeWordEngine = WakeWordEngine(recognizer, matcher)
}
