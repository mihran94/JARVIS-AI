package com.jarvisblue.core.common

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TextToolsTest {

    @Test
    fun `normalize removes punctuation and case`() {
        assertEquals("hey jarvis blue", TextTools.normalize("Hey, Jarvis Blue!"))
    }

    @Test
    fun `similarity of identical strings is one`() {
        assertEquals(1.0, TextTools.similarity("open alarm", "open alarm"), 0.0001)
    }

    @Test
    fun `similarity detects disjoint strings`() {
        assertEquals(0.0, TextTools.similarity("alpha beta", "gamma delta"), 0.0001)
    }

    @Test
    fun `fuzzy similarity tolerates asr noise`() {
        val score = TextTools.fuzzySimilarity("hey jarvis blue", "hey jarvis bloo")
        assertTrue("expected high fuzzy score, got $score", score > 0.6)
    }

    @Test
    fun `levenshtein counts single edits`() {
        assertEquals(1, TextTools.levenshtein("kitten", "kitteh"))
        assertEquals(3, TextTools.levenshtein("kitten", "sitting"))
    }
}
