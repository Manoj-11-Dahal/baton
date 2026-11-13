import { contextBridge, ipcRenderer } from 'electron';

const invoke = (method: string, params?: any): Promise<any> => ipcRenderer.invoke(method, params);

contextBridge.exposeInMainWorld('batonApi', {
  invoke,
  on: (channel: string, listener: (e: any) => void) => {
    ipcRenderer.on(channel, (_event, arg) => listener(arg));
    return () => ipcRenderer.removeAllListeners(channel);
  },
  send: (channel: string, ...args: any[]) => ipcRenderer.send(channel, ...args),
});
