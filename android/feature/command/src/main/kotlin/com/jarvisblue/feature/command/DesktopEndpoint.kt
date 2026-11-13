package com.jarvisblue.feature.command

import java.net.URI

/** The remote never downgrades a Windows control connection to plaintext. */
object DesktopEndpoint {
    fun baseUrl(host: String, port: Int): String {
        require(port in 1..65535) { "Choose a valid Windows bridge port" }
        val value = host.trim()
        require(value.isNotEmpty()) { "Enter the Windows bridge address" }
        val origin = if (value.contains("://")) value else "https://$value"
        val uri = try {
            URI(origin)
        } catch (_: Exception) {
            throw IllegalArgumentException("Invalid HTTPS Windows bridge address")
        }
        require(uri.scheme == "https" && uri.host != null) {
            "Only HTTPS Windows bridge addresses are allowed"
        }
        require(uri.rawUserInfo == null && uri.rawQuery == null &&
                uri.rawFragment == null && (uri.rawPath == null || uri.rawPath == "" ||
                uri.rawPath == "/") && uri.rawAuthority != null) {
            "Windows bridge address must contain only a hostname and port"
        }
        require(uri.port == -1 || uri.port == port) {
            "Bridge address contains a conflicting port"
        }
        return URI("https", null, uri.host, port, null, null, null).toASCIIString()
    }
}
