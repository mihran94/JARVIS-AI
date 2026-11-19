package com.jarvisblue.core.common

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PairingCodeTest {

    private val secret = "shared-secret-for-tests-0123456789abcdef"
    private val fingerprint = "b".repeat(64)

    private fun code(
        bridge: String = "https://pc.example.lan:8765",
        fp: String? = fingerprint,
        expires: String = "1764000000",
    ): String {
        val lines = mutableListOf(
            PairingCode.FORMAT,
            "bridge=$bridge",
            "key=jarvis-iphone-v1",
            "secret=$secret",
            "expires=$expires",
        )
        if (fp != null) lines.add("fp=$fp")
        return lines.joinToString("\n")
    }

    @Test
    fun `a whole pairing code gives the address, the secret and the fingerprint`() {
        val details = PairingCode.parse(code())
        assertTrue(details.wasPairingCode)
        assertEquals(secret, details.secret)
        assertEquals("pc.example.lan", details.host)
        assertEquals(8765, details.port)
        assertEquals(fingerprint, details.fingerprint)
        assertEquals(1764000000L, details.expiresAt)
    }

    @Test
    fun `a bare secret is still accepted`() {
        val details = PairingCode.parse(secret)
        assertFalse(details.wasPairingCode)
        assertEquals(secret, details.secret)
        assertEquals("", details.host)
        assertEquals(0, details.port)
        assertNull(details.fingerprint)
    }

    @Test
    fun `a code without a fingerprint has no fingerprint to pin`() {
        val details = PairingCode.parse(code(fp = null))
        assertNull(details.fingerprint)
        assertEquals(secret, details.secret)
    }

    @Test
    fun `a damaged fingerprint is not used`() {
        val details = PairingCode.parse(code(fp = "not-a-fingerprint"))
        assertNull(details.fingerprint)
        assertEquals(secret, details.secret)
    }

    @Test
    fun `a short secret is refused`() {
        var refused = false
        try {
            PairingCode.parse("too-short")
        } catch (error: IllegalArgumentException) {
            refused = true
        }
        assertTrue("a secret that is too short must be refused", refused)
    }

    @Test
    fun `a code without a secret is refused`() {
        var refused = false
        try {
            PairingCode.parse("${PairingCode.FORMAT}\nbridge=https://pc.example.lan:8765")
        } catch (error: IllegalArgumentException) {
            refused = true
        }
        assertTrue(refused)
    }

    @Test
    fun `nothing at all is refused`() {
        var refused = false
        try {
            PairingCode.parse("")
        } catch (error: IllegalArgumentException) {
            refused = true
        }
        assertTrue(refused)
    }

    @Test
    fun `a code pasted as one line is read the same`() {
        // The field the owner pastes into takes one line, so the code
        // arrives with its lines joined by spaces.
        val oneLine = code().replace("\n", " ")
        val details = PairingCode.parse(oneLine)
        assertTrue(details.wasPairingCode)
        assertEquals(secret, details.secret)
        assertEquals("pc.example.lan", details.host)
        assertEquals(8765, details.port)
        assertEquals(fingerprint, details.fingerprint)
    }

    @Test
    fun `what the owner typed wins over the code`() {
        val details = PairingCode.parse(code())
        assertEquals("typed.example.lan", details.mergeHost("typed.example.lan"))
        assertEquals("9999", details.mergePort("9999"))
    }

    @Test
    fun `the code fills in what the owner left empty`() {
        val details = PairingCode.parse(code())
        assertEquals("pc.example.lan", details.mergeHost(""))
        assertEquals("8765", details.mergePort(""))
    }

    @Test
    fun `a bare secret leaves the address to the owner`() {
        val details = PairingCode.parse(secret)
        assertEquals("", details.mergeHost(""))
        assertEquals("", details.mergePort(""))
    }

    @Test
    fun `the address without a port is still read`() {
        val details = PairingCode.parse(code(bridge = "https://pc.example.lan"))
        assertEquals("pc.example.lan", details.host)
        assertEquals(0, details.port)
    }

    @Test
    fun `a code that has expired is expired`() {
        val details = PairingCode.parse(code(expires = "1764000000"))
        assertTrue(details.isExpired(1764000000L))
        assertTrue(details.isExpired(1764000001L))
        assertFalse(details.isExpired(1763999999L))
    }

    @Test
    fun `a bare secret is not expired by the clock`() {
        val details = PairingCode.parse(secret)
        assertFalse(details.isExpired(1764000000L))
        assertFalse(details.isExpired(Long.MAX_VALUE))
    }

    @Test
    fun `a code without an expiry is not expired`() {
        val details = PairingCode.parse(code(expires = "0"))
        assertEquals(0L, details.expiresAt)
        assertFalse(details.isExpired(1764000000L))
    }
}
