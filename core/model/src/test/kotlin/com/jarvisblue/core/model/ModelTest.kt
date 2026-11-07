package com.jarvisblue.core.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ModelTest {

    @Test
    fun `language resolves from regional tag`() {
        assertEquals(Language.TAMIL, Language.fromTag("ta-IN"))
        assertEquals(Language.ENGLISH, Language.fromTag("en-GB"))
        assertEquals(Language.FRENCH, Language.fromTag("fr"))
        assertNull(Language.fromTag("de"))
        assertNull(Language.fromTag(null))
    }

    @Test
    fun `risk levels compare by score`() {
        assertTrue(RiskLevel.CRITICAL.atLeast(RiskLevel.HIGH))
        assertTrue(RiskLevel.HIGH.atLeast(RiskLevel.HIGH))
        assertTrue(!RiskLevel.LOW.atLeast(RiskLevel.HIGH))
    }

    @Test
    fun `provider offline fallback cannot run tools`() {
        assertTrue(!ProviderId.OFFLINE_ECHO.supportsTools)
        assertTrue(ProviderId.OPENAI.supportsTools)
    }
}
