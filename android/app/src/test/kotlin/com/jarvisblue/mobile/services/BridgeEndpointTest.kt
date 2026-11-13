package com.jarvisblue.mobile.services

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class BridgeEndpointTest {
    @Test fun bareHostUsesHttps() {
        assertEquals("https://pc.example.lan:8765", BridgeEndpoint.baseUrl("pc.example.lan", 8765))
    }

    @Test fun existingHttpsPortIsNotDuplicated() {
        assertEquals("https://pc.example.lan:8765",
            BridgeEndpoint.baseUrl("https://pc.example.lan:8765/", 8765))
    }

    @Test fun ipv6IsSupported() {
        assertEquals("https://[::1]:8765", BridgeEndpoint.baseUrl("[::1]", 8765))
    }

    @Test fun plaintextAndEmbeddedCredentialsAreRejected() {
        assertThrows(IllegalArgumentException::class.java) {
            BridgeEndpoint.baseUrl("http://pc.example.lan", 8765)
        }
        assertThrows(IllegalArgumentException::class.java) {
            BridgeEndpoint.baseUrl("https://user:pass@pc.example.lan", 8765)
        }
    }

    @Test fun pathQueryAndConflictingPortAreRejected() {
        listOf("https://pc.example.lan/api", "https://pc.example.lan/?token=abc",
            "https://pc.example.lan:9999").forEach { input ->
            assertThrows(IllegalArgumentException::class.java) {
                BridgeEndpoint.baseUrl(input, 8765)
            }
        }
    }

    @Test fun invalidPortsAreRejected() {
        for (port in listOf(0, 65536)) {
            assertThrows(IllegalArgumentException::class.java) {
                BridgeEndpoint.baseUrl("pc.example.lan", port)
            }
        }
    }
}
