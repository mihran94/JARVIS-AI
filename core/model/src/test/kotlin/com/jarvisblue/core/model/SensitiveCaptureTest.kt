package com.jarvisblue.core.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The rules of the sensitive captures.
 *
 * These are the rules that decide what the assistant may read, so they are
 * checked without a device.
 */
class SensitiveCaptureTest {

    @Test fun nothingIsAllowedByDefault() {
        val consent = CaptureConsent()
        assertTrue(consent.allowed.isEmpty())
        for (capture in SensitiveCapture.entries) {
            assertFalse("The default must deny ${capture.id}", consent.allows(capture))
        }
    }

    @Test fun theEmptyConsentIsTheSameAsTheDefault() {
        assertEquals(CaptureConsent.NONE.allowed, CaptureConsent().allowed)
        assertFalse(CaptureConsent.NONE.allows(SensitiveCapture.MICROPHONE))
    }

    @Test fun onlyWhatWasGrantedIsAllowed() {
        val consent = CaptureConsent(setOf(SensitiveCapture.MICROPHONE))
        assertTrue(consent.allows(SensitiveCapture.MICROPHONE))
        assertFalse(consent.allows(SensitiveCapture.SCREEN_READING))
        assertFalse(consent.allows(SensitiveCapture.NOTIFICATION_CONTENT))
        assertFalse(consent.allows(SensitiveCapture.BACKGROUND_SERVICE))
    }

    @Test fun aCaptureIsIndependentOfTheOthers() {
        val consent = CaptureConsent(setOf(SensitiveCapture.NOTIFICATION_CONTENT))
        assertEquals(
            listOf(
                SensitiveCapture.MICROPHONE,
                SensitiveCapture.SCREEN_READING,
                SensitiveCapture.BACKGROUND_SERVICE,
            ),
            consent.denied(),
        )
        assertTrue(consent.allowsAny(listOf(SensitiveCapture.SCREEN_READING, SensitiveCapture.NOTIFICATION_CONTENT)))
        assertFalse(consent.allowsAny(listOf(SensitiveCapture.SCREEN_READING, SensitiveCapture.MICROPHONE)))
    }

    @Test fun everyCaptureNeedsASensitivePermission() {
        for (capture in SensitiveCapture.entries) {
            assertTrue(
                "${capture.id} must be a sensitive bucket",
                capture.permission.sensitive,
            )
        }
    }

    @Test fun everyCaptureHasItsOwnPermission() {
        val permissions = SensitiveCapture.entries.map { it.permission }
        assertEquals("Two captures must not share a bucket", permissions.size, permissions.toSet().size)
    }

    @Test fun theIdsAreUniqueAndStable() {
        val ids = SensitiveCapture.entries.map { it.id }
        assertEquals(ids.size, ids.toSet().size)
        // The ids are written into the encrypted grant file, so they are part
        // of the contract and must not change.
        assertEquals(
            listOf(
                "microphone.capture",
                "accessibility.screen",
                "notifications.content",
                "background.service",
            ),
            ids,
        )
    }

    @Test fun thePermissionIdsMatchTheCaptureIds() {
        assertEquals("microphone", SensitiveCapture.MICROPHONE.permission.id)
        assertEquals("accessibility", SensitiveCapture.SCREEN_READING.permission.id)
        assertEquals("notifications.read", SensitiveCapture.NOTIFICATION_CONTENT.permission.id)
        assertEquals("background.service", SensitiveCapture.BACKGROUND_SERVICE.permission.id)
    }

    @Test fun everyCaptureHasALabelAndADescription() {
        for (capture in SensitiveCapture.entries) {
            assertTrue(capture.label.isNotBlank())
            assertTrue(capture.description.length > 20)
        }
    }
}
