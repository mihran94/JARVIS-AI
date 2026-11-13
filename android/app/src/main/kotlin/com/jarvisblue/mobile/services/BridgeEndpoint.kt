package com.jarvisblue.mobile.services

import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/**
 * Converts a paired Windows peer into a secure bridge endpoint.
 *
 * The stored host may be a bare hostname/IP or a full HTTPS origin. Never
 * silently downgrade to HTTP, include credentials, or append a second port.
 * Invalid settings are reported as an offline/degraded peer by the gateway.
 */
internal object BridgeEndpoint {
    fun baseUrl(host: String, port: Int): String {
        require(port in 1..65535) { "Invalid bridge port" }
        val input = host.trim()
        require(input.isNotEmpty()) { "A bridge host is required" }
        val origin = if (input.contains("://")) input else "https://$input"
        val url = origin.toHttpUrlOrNull()
            ?: throw IllegalArgumentException("Invalid bridge endpoint")
        require(url.scheme == "https") { "Windows bridge requires HTTPS" }
        require(url.username.isEmpty() && url.password.isEmpty()) { "Bridge URL cannot contain credentials" }
        require(url.encodedPath == "/" && url.query == null && url.fragment == null) {
            "Bridge host must be an origin without a path, query or fragment"
        }
        require(url.port == 443 || url.port == port) { "Conflicting bridge ports" }
        return url.newBuilder().port(port).build().toString().removeSuffix("/")
    }
}
