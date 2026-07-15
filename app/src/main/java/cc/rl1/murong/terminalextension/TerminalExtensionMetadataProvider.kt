package cc.rl1.murong.terminalextension

import android.content.ContentProvider
import android.content.ContentValues
import android.database.Cursor
import android.database.MatrixCursor
import android.net.Uri

class TerminalExtensionMetadataProvider : ContentProvider() {

    override fun onCreate(): Boolean = true

    override fun query(
        uri: Uri,
        projection: Array<out String>?,
        selection: String?,
        selectionArgs: Array<out String>?,
        sortOrder: String?
    ): Cursor {
        val columns = arrayOf(
            "packageName",
            "extensionVersion",
            "bootstrapReady",
            "fullToolchainReady",
            "downloadMode",
            "notes"
        )
        return MatrixCursor(columns).apply {
            addRow(
                arrayOf<Any>(
                    BuildConfig.APPLICATION_ID,
                    BuildConfig.APP_VERSION_NAME,
                    0,
                    0,
                    "bundled",
                    "Headless terminal extension package. No launcher UI. Bundled toolchain version: " +
                        BuildConfig.BUNDLED_TOOLCHAIN_VERSION +
                        ", ABI: " + BuildConfig.BUNDLED_TOOLCHAIN_ABI
                )
            )
        }
    }

    override fun getType(uri: Uri): String = "vnd.android.cursor.item/vnd.${BuildConfig.APPLICATION_ID}.metadata"

    override fun insert(uri: Uri, values: ContentValues?): Uri? = null

    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?): Int = 0

    override fun update(
        uri: Uri,
        values: ContentValues?,
        selection: String?,
        selectionArgs: Array<out String>?
    ): Int = 0
}
