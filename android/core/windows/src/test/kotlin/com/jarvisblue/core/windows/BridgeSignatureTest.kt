package com.jarvisblue.core.windows

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

/**
 * Cross-implementation test vector.
 *
 * The same canonical string is produced by the Windows bridge
 * (`windows-bridge/jarvis_bridge/server.py`) and by this client. If either side
 * changes the scheme, these vectors fail and the two halves stop interoperating.
 */
class BridgeSignatureTest {

    @Test
    fun `sha256 of empty body matches the python reference`() {
        assertEquals(
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            BridgeClient.sha256Hex(""),
        )
    }

    @Test
    fun `hmac signature matches the python reference`() {
        val signature = BridgeClient.sign(
            method = "GET",
            path = "/api/status",
            timestamp = "1700000000000",
            body = "",
            secret = "test-secret",
            nonce = "nonce-123",
        )
        assertEquals(
            "5a0eff83c8875fc160be921c708461920dfa3f9775821784555822eb38d32a3d",
            signature,
        )
    }

    @Test
    fun `different nonces produce different signatures`() {
        val a = BridgeClient.sign("GET", "/api/status", "1700000000000", "", "secret", "nonce-a")
        val b = BridgeClient.sign("GET", "/api/status", "1700000000000", "", "secret", "nonce-b")
        assertEquals(false, a == b)
    }

    @Test
    fun `body is part of the signature so payloads cannot be swapped`() {
        val a = BridgeClient.sign("POST", "/api/jobs", "1700000000000", "{\"a\":1}", "secret", "n")
        val b = BridgeClient.sign("POST", "/api/jobs", "1700000000000", "{\"a\":2}", "secret", "n")
        assertEquals(false, a == b)
    }

    @Test
    fun `control endpoints reject plaintext and invalid origins`() {
        assertEquals("https://pc.example:8765", BridgeClient.secureEndpoint("https://pc.example:8765"))
        for (origin in listOf(
            "http://pc.example:8765", "https://user:pw@pc.example:8765",
            "https://pc.example:8765/api", "https://pc.example?secret=x",
            "ftp://pc.example", "https://"
        )) {
            assertThrows(IllegalArgumentException::class.java) {
                BridgeClient.secureEndpoint(origin)
            }
        }
    }
}
