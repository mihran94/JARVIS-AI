package com.jarvisblue.core.voice

import com.jarvisblue.core.model.Language
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class WakePhraseMatcherTest {

    private val matcher = WakePhraseMatcher()

    @Test
    fun `matches the exact wake phrase`() {
        val match = matcher.match("Hey Jarvis Blue", Language.ENGLISH)
        assertTrue(match.isWakeCall)
    }

    @Test
    fun `matches when the phrase is embedded in a sentence`() {
        val match = matcher.match("Hey Jarvis Blue what is the weather", Language.ENGLISH)
        assertTrue(match.isWakeCall)
    }

    @Test
    fun `tolerates recognition noise`() {
        val match = matcher.match("Hey Jarvis bloo", Language.ENGLISH)
        assertTrue("expected a wake call, got $match", match.isWakeCall)
    }

    @Test
    fun `does not match unrelated speech`() {
        val match = matcher.match("the weather is nice today", Language.ENGLISH)
        assertFalse(match.isWakeCall)
    }

    @Test
    fun `matches the tamil transliteration`() {
        val match = matcher.match("ஹே ஜார்விஸ் புளூ", Language.TAMIL)
        assertTrue(match.isWakeCall)
        assertEquals(Language.TAMIL, match.language)
    }

    @Test
    fun `matches the french greeting`() {
        val match = matcher.match("salut jarvis", Language.FRENCH)
        assertTrue(match.isWakeCall)
    }

    @Test
    fun `extracts the command that follows the phrase`() {
        val command = matcher.extractCommand("hey jarvis blue organize my downloads")
        assertNotNull(command)
        assertTrue(command!!.contains("organize"))
    }

    @Test
    fun `extracts nothing when only the wake phrase was said`() {
        assertEquals(null, matcher.extractCommand("hey jarvis blue"))
    }
}
