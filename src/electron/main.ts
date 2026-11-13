import { app, BrowserWindow, ipcMain, dialog } from 'electron';
import path from 'node:path';
import { Core } from '../core/index';

let mainWindow: BrowserWindow | null = null;
let core: Core | null = null;

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: 'Agi Super Harness',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, '..', 'index.html'));

  mainWindow.once('ready-to-show', () => {
    mainWindow?.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(async () => {
  const dataDir = app.getPath('userData');
  core = new Core({
    dataDir,
    platform: process.platform,
    isElectron: true,
    version: app.getVersion(),
    homeDir: app.getPath('home'),
    pathSep: require('node:path').sep,
    secureStorage: false,
    versions: { node: process.version, electron: process.versions.electron, chrome: process.versions.chrome },
  });
  await core.init();
  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

/* ──────────────── IPC handlers ──────────────── */

function withCore<T>(fn: (c: Core) => T): T {
  if (!core) throw new Error('Core not initialized');
  return fn(core);
}

ipcMain.handle('app.bootstrap', () => withCore((c) => c.bootstrap()));

ipcMain.handle('settings.update', (_, p) => withCore((c) => c.settingsUpdate(p)));
ipcMain.handle('settings.reset', () => withCore((c) => c.settingsReset()));
ipcMain.handle('settings.export', () => withCore((c) => c.settingsExport()));
ipcMain.handle('settings.import', (_, p) => withCore((c) => c.settingsImport(p.json)));

ipcMain.handle('provider.save', (_, p) => withCore((c) => c.providerSave(p)));
ipcMain.handle('provider.remove', (_, p) => withCore((c) => c.providerRemove(p)));
ipcMain.handle('provider.test', async (_, p) => withCore((c) => c.providerTest(p)));
ipcMain.handle('provider.fetchModels', async (_, p) => withCore((c) => c.providerFetchModels(p)));

ipcMain.handle('workspace.add', (_, p) => withCore((c) => c.workspaceAdd(p)));
ipcMain.handle('workspace.update', (_, p) => withCore((c) => c.workspaceUpdate(p)));
ipcMain.handle('workspace.remove', (_, p) => withCore((c) => c.workspaceRemove(p)));
ipcMain.handle('workspace.info', (_, p) => withCore((c) => c.workspaceInfo(p)));

ipcMain.handle('thread.send', (_, p) => withCore((c) => c.threadSend(p)));
ipcMain.handle('thread.stop', (_, p) => withCore((c) => c.threadStop(p)));
ipcMain.handle('thread.retry', (_, p) => withCore((c) => c.threadRetry(p)));
ipcMain.handle('thread.get', (_, p) => withCore((c) => c.threadGet(p)));
ipcMain.handle('thread.update', (_, p) => withCore((c) => c.threadUpdate(p)));
ipcMain.handle('thread.remove', () => withCore((c) => c.threadRemove()));
ipcMain.handle('thread.clearAll', () => withCore((c) => c.threadRemove()));
ipcMain.handle('thread.context', (_, p) => withCore((c) => c.threadContext(p)));

ipcMain.handle('approval.respond', (_, p) => withCore((c) => c.approvalRespond(p)));

ipcMain.handle('native.pickFolder', async () => {
  const result = await dialog.showOpenDialog({ properties: ['openDirectory'] });
  return { path: result.filePaths[0] ?? null };
});

ipcMain.handle('native.reveal', async (_, p) => {
  await shell.showItemInFolder(p.path);
});

ipcMain.handle('native.openExternal', async (_, p) => {
  await require('electron').shell.openExternal(p.url);
});

ipcMain.handle('native.window', async (_, p) => {
  const win = mainWindow;
  if (!win) return { maximized: false };
  if (p.action === 'minimize') win.minimize();
  else if (p.action === 'maximize') win.maximize();
  else if (p.action === 'close') win.close();
  else if (p.action === 'state') return { maximized: win.isMaximized() };
  return { maximized: win.isMaximized() };
});

const shell = require('electron').shell;

app.on('before-quit', async () => {
  await core?.shutdown();
});
