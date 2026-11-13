package com.jarvisblue.core.tools

import com.jarvisblue.core.model.Language
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class IntentRouterTest {

    private val router = IntentRouter()

    @Test
    fun `detects the download organisation command`() {
        val intent = router.detect("Jarvis, organize my downloaded PDF files.")
        assertEquals(IntentRouter.IntentType.ORGANIZE_FILES, intent.type)
        assertTrue(intent.confidence > 0.6)
    }

    @Test
    fun `detects the project opening command`() {
        val intent = router.detect("Jarvis, open my development project.")
        assertEquals(IntentRouter.IntentType.OPEN_PROJECT, intent.type)
    }

    @Test
    fun `detects the explain code command and the requested language`() {
        val intent = router.detect("Jarvis, explain this code in Tamil.")
        assertEquals(IntentRouter.IntentType.EXPLAIN_CODE, intent.type)
        assertEquals(Language.TAMIL, router.explanationLanguage(intent.slots))
    }

    @Test
    fun `detects the reminder command`() {
        val intent = router.detect("Jarvis, remind me about tomorrow's appointment.")
        assertEquals(IntentRouter.IntentType.SET_REMINDER, intent.type)
    }

    @Test
    fun `detects the windows render job command`() {
        val intent = router.detect("Jarvis, check the progress of my Windows render job.")
        assertEquals(IntentRouter.IntentType.CHECK_REMOTE_JOB, intent.type)
    }

    @Test
    fun `detects the security inspection command`() {
        val intent = router.detect("Jarvis, inspect this application for security issues.")
        assertEquals(IntentRouter.IntentType.SECURITY_REVIEW, intent.type)
    }

    @Test
    fun `falls back to general chat for unrelated text`() {
        val intent = router.detect("What is the capital of France?")
        assertEquals(IntentRouter.IntentType.GENERAL_CHAT, intent.type)
    }
}
