// The history backup the phone may ask the PC for.
//
// The history itself is never sent over the bridge. The PC makes the
// backup, keeps it on the PC, and the phone is told the name, the size
// and the checksum of what was made. The owner approves it on the PC,
// through the same one-use gate as every other action.
//
// These names are the contract with the desktop: `remote/jobs.py` accepts
// exactly these two actions and refuses anything else.

/** The action that asks the PC to back the history up. */
export const HISTORY_BACKUP_ACTION = 'backup_history';

/** The action that asks the PC to restore a backup it named. */
export const HISTORY_RESTORE_ACTION = 'restore_history';

/** The end a backup file has. */
export const BACKUP_SUFFIX = '.jarvisbak';

/**
 * Whether a backup name is one the desktop may be asked for.
 *
 * Only a plain file name is allowed. A phone can never point the
 * restore at a path of its own choosing.
 */
export function isSafeBackupName(name) {
  if (typeof name !== 'string' || name.length === 0) {
    return false;
  }
  if (name.includes('/') || name.includes('\\')) {
    return false;
  }
  if (name.includes('..')) {
    return false;
  }
  return name.endsWith(BACKUP_SUFFIX);
}

/** The task that asks the PC to back the history up. */
export function backupTask(title = 'Back up the conversation history') {
  return {
    kind: 'CUSTOM',
    title,
    payload: JSON.stringify({ action: HISTORY_BACKUP_ACTION }),
    requireApproval: true,
  };
}

/** The task that asks the PC to restore the backup it names. */
export function restoreTask(name, title = 'Restore a conversation history backup') {
  return {
    kind: 'CUSTOM',
    title,
    payload: JSON.stringify({ action: HISTORY_RESTORE_ACTION, backup: name }),
    requireApproval: true,
  };
}
