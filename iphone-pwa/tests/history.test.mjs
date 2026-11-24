// The history backup contract between the phone and the desktop.
//
// The desktop accepts exactly these two actions and refuses anything
// else, so the names here and the names in `remote/jobs.py` have to
// agree.

import test from 'node:test';
import assert from 'node:assert/strict';

import {
  BACKUP_SUFFIX, HISTORY_BACKUP_ACTION, HISTORY_RESTORE_ACTION, backupTask,
  isSafeBackupName, restoreTask,
} from '../js/history.js';

test('the backup task asks for the backup action', () => {
  const task = backupTask();
  assert.equal(task.kind, 'CUSTOM');
  assert.equal(task.requireApproval, true);
  assert.deepEqual(JSON.parse(task.payload), { action: HISTORY_BACKUP_ACTION });
});

test('the restore task names the backup it wants', () => {
  const task = restoreTask('phone-history-20261124-101500.jarvisbak');
  assert.deepEqual(JSON.parse(task.payload), {
    action: HISTORY_RESTORE_ACTION,
    backup: 'phone-history-20261124-101500.jarvisbak',
  });
});

test('only a plain backup name is allowed', () => {
  assert.equal(isSafeBackupName('phone-history-20261124-101500.jarvisbak'), true);
  assert.equal(isSafeBackupName('../secrets.jarvisbak'), false);
  assert.equal(isSafeBackupName('folder/backup.jarvisbak'), false);
  assert.equal(isSafeBackupName('folder\\backup.jarvisbak'), false);
  assert.equal(isSafeBackupName('backup.txt'), false);
  assert.equal(isSafeBackupName(''), false);
  assert.equal(isSafeBackupName(undefined), false);
});

test('the suffix is the one the desktop writes', () => {
  assert.equal(BACKUP_SUFFIX, '.jarvisbak');
});
