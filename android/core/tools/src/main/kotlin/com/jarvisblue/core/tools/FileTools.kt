package com.jarvisblue.core.tools

import android.content.ContentResolver
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.DocumentsContract
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * File organisation through the Storage Access Framework.
 *
 * The app never holds broad storage permission. The user grants a *tree* URI
 * through the system document picker; the app can then read and write only
 * inside that tree, and the grant is revocable from Android settings at any time.
 */
class FileTools(private val context: Context) {

    /** Intent the app shows so the user can pick a folder to work in. */
    fun folderPickerIntent(): Intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
        addFlags(
            Intent.FLAG_GRANT_READ_URI_PERMISSION or
                Intent.FLAG_GRANT_WRITE_URI_PERMISSION or
                Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION,
        )
    }

    fun takePersistablePermission(treeUri: Uri): Boolean = runCatching {
        context.contentResolver.takePersistableUriPermission(
            treeUri,
            Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
        )
        true
    }.getOrDefault(false)

    fun hasPermission(treeUri: Uri): Boolean = runCatching {
        context.contentResolver.persistedUriPermissions.any { it.uri == treeUri && it.isWritePermission }
    }.getOrDefault(false)

    data class ScannedFile(
        val documentId: String,
        val name: String,
        val mimeType: String,
        val sizeBytes: Long,
        val relativePath: String,
    )

    suspend fun listFiles(treeUri: Uri, extension: String? = null): List<ScannedFile> =
        withContext(Dispatchers.IO) {
            val resolver = context.contentResolver
            val childrenUri = DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, DocumentsContract.getTreeDocumentId(treeUri))
            val results = mutableListOf<ScannedFile>()
            resolver.query(childrenUri, null, null, null, null)?.use { cursor ->
                val idIndex = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_DOCUMENT_ID)
                val nameIndex = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_DISPLAY_NAME)
                val mimeIndex = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_MIME_TYPE)
                val sizeIndex = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_SIZE)
                while (cursor.moveToNext()) {
                    val name = if (nameIndex >= 0) cursor.getString(nameIndex).orEmpty() else ""
                    val mime = if (mimeIndex >= 0) cursor.getString(mimeIndex).orEmpty() else ""
                    if (mime == DocumentsContract.Document.MIME_TYPE_DIR) continue
                    if (extension != null && !name.endsWith(".$extension", ignoreCase = true)) continue
                    results += ScannedFile(
                        documentId = if (idIndex >= 0) cursor.getString(idIndex).orEmpty() else "",
                        name = name,
                        mimeType = mime,
                        sizeBytes = if (sizeIndex >= 0) cursor.getLong(sizeIndex) else 0L,
                        relativePath = name,
                    )
                }
            }
            results
        }

    /**
     * Groups files by extension into sub-folders.
     *
     * Files are **copied**, never moved, unless [moveConfirmed] is true — moving
     * destroys the original path, so it must be an explicit, confirmed action.
     */
    suspend fun organizeByExtension(
        treeUri: Uri,
        extension: String? = null,
        moveConfirmed: Boolean = false,
        dryRun: Boolean = true,
    ): String = withContext(Dispatchers.IO) {
        val files = listFiles(treeUri, extension)
        if (files.isEmpty()) {
            return@withContext "No matching files found in the granted folder."
        }

        val grouped = files.groupBy { file ->
            file.name.substringAfterLast('.', "other").lowercase().ifBlank { "other" }
        }

        if (dryRun) {
            return@withContext buildString {
                append("Dry run — nothing was changed. ")
                append("Found ${files.size} file(s) in the granted folder:\n")
                grouped.forEach { (ext, group) ->
                    append("• .$ext → ${group.size} file(s): ")
                    append(group.take(5).joinToString(", ") { it.name })
                    if (group.size > 5) append(", …")
                    append("\n")
                }
                append("Run again without dry-run to create the folders and copy the files.")
            }
        }

        val resolver = context.contentResolver
        val created = mutableListOf<String>()
        val copied = mutableListOf<String>()
        val failures = mutableListOf<String>()

        for ((ext, group) in grouped) {
            val folderName = ext.uppercase()
            val folderUri = runCatching { ensureFolder(treeUri, folderName) }.getOrNull()
            if (folderUri == null) {
                failures += "Could not create folder $folderName"
                continue
            }
            created += folderName
            for (file in group) {
                val sourceUri = DocumentsContract.buildDocumentUriUsingTree(treeUri, file.documentId)
                val targetUri = runCatching {
                    DocumentsContract.createDocument(resolver, folderUri, mimeOf(file.name), file.name)
                }.getOrNull()
                if (targetUri == null) {
                    failures += "Could not copy ${file.name}"
                    continue
                }
                val ok = runCatching {
                    val input = resolver.openInputStream(sourceUri) ?: return@runCatching false
                    val output = resolver.openOutputStream(targetUri) ?: return@runCatching false
                    input.use { source ->
                        output.use { sink -> source.copyTo(sink) }
                    }
                    true
                }.getOrDefault(false)

                if (ok) {
                    copied += file.name
                    if (moveConfirmed) {
                        runCatching { DocumentsContract.deleteDocument(resolver, sourceUri) }
                    }
                } else {
                    failures += "Copy failed for ${file.name}"
                }
            }
        }

        buildString {
            append("Organised ${copied.size} file(s) into ${created.size} folder(s): ")
            append(created.joinToString(", "))
            if (copied.isNotEmpty()) {
                append(". Copied: ")
                append(copied.take(8).joinToString(", "))
                if (copied.size > 8) append(", …")
            }
            if (moveConfirmed) append(". Originals were removed (move mode confirmed).")
            else append(". Originals were left in place — nothing was deleted.")
            if (failures.isNotEmpty()) {
                append(". Issues: ")
                append(failures.take(5).joinToString("; "))
            }
        }
    }

    private fun ensureFolder(treeUri: Uri, name: String): Uri {
        val resolver = context.contentResolver
        val rootDocId = DocumentsContract.getTreeDocumentId(treeUri)
        val childrenUri = DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, rootDocId)
        resolver.query(childrenUri, null, null, null, null)?.use { cursor ->
            val idIndex = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_DOCUMENT_ID)
            val nameIndex = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_DISPLAY_NAME)
            val mimeIndex = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_MIME_TYPE)
            while (cursor.moveToNext()) {
                val mime = if (mimeIndex >= 0) cursor.getString(mimeIndex) else null
                val label = if (nameIndex >= 0) cursor.getString(nameIndex) else null
                if (mime == DocumentsContract.Document.MIME_TYPE_DIR && label.equals(name, ignoreCase = true)) {
                    return DocumentsContract.buildDocumentUriUsingTree(treeUri, cursor.getString(idIndex))
                }
            }
        }
        return DocumentsContract.createDocument(
            resolver,
            treeUri,
            DocumentsContract.Document.MIME_TYPE_DIR,
            name,
        ) ?: throw IllegalStateException("Folder creation failed")
    }

    private fun mimeOf(name: String): String = when (name.substringAfterLast('.', "").lowercase()) {
        "pdf" -> "application/pdf"
        "png" -> "image/png"
        "jpg", "jpeg" -> "image/jpeg"
        "txt", "md" -> "text/plain"
        else -> "application/octet-stream"
    }

    /** Lists a small preview of files for the UI. */
    suspend fun preview(treeUri: Uri, limit: Int = 20): JsonObject = withContext(Dispatchers.IO) {
        val files = listFiles(treeUri).take(limit)
        buildJsonObject {
            put("count", files.size)
            put("files", buildJsonArray {
                files.forEach { file ->
                    add(
                        buildJsonObject {
                            put("name", file.name)
                            put("sizeBytes", file.sizeBytes)
                            put("mimeType", file.mimeType)
                        },
                    )
                }
            })
        }
    }
}
