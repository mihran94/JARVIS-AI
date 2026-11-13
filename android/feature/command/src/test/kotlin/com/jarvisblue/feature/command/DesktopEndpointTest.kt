package com.jarvisblue.feature.command

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class DesktopEndpointTest {
    @Test fun createsStrictHttpsOriginFromPrivateName() {
        assertEquals("https://pc.tailnet.ts.net:8765",
            DesktopEndpoint.baseUrl("pc.tailnet.ts.net", 8765))
        assertEquals("https://pc.tailnet.ts.net:8765",
            DesktopEndpoint.baseUrl("https://pc.tailnet.ts.net:8765", 8765))
    }

    @Test fun rejectsInsecureOrMaliciousEndpoints() {
        for (host in listOf(
            "http://pc.local", "ftp://pc.local", "https://user:pass@pc.local",
            "https://pc.local/api/jobs", "https://pc.local?token=secret",
            "https://pc.local#fragment", "https://pc.local:9999",
            "https://"
        )) {
            assertThrows(IllegalArgumentException::class.java) {
                DesktopEndpoint.baseUrl(host, 8765)
            }
        }
        assertThrows(IllegalArgumentException::class.java) {
            DesktopEndpoint.baseUrl("pc.local", 0)
        }
    }
}
