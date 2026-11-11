const vscode = require('vscode');
const fs = require('fs');
const path = require('path');

function directory() {
  const local = Object.entries(process.env).find(([key]) => key.toUpperCase() === 'LOCALAPPDATA');
  if (!local) throw new Error('local application data unavailable');
  return path.join(local[1], 'JarvisAI', 'workspace-requests');
}

function readRequest(id) {
  if (!/^[a-f0-9]{32}$/.test(id)) throw new Error('invalid request');
  const filename = path.join(directory(), id + '.json');
  if (fs.statSync(filename).size > 4096) throw new Error('request too large');
  const request = JSON.parse(fs.readFileSync(filename, 'utf8'));
  if (request.id !== id || request.project_id !== 'jarvis-ai' ||
      !Number.isFinite(request.expires) || request.expires <= Date.now()/1000 ||
      request.expires > Date.now()/1000 + 30 || !path.isAbsolute(request.folder)) {
    throw new Error('expired or invalid request');
  }
  return request;
}

function canonicalFolder(folder) {
  return fs.realpathSync.native(folder).toLowerCase();
}

async function verify(context, id) {
  const request = readRequest(id);
  const folders = vscode.workspace.workspaceFolders || [];
  if (folders.length !== 1 || folders[0].uri.scheme !== 'file' ||
      canonicalFolder(folders[0].uri.fsPath) !== canonicalFolder(request.folder)) return false;
  const receipt = {id, project_id: request.project_id, folder: folders[0].uri.fsPath,
                   verified_at: Date.now()/1000, method: 'vscode_workspace_api'};
  const target = path.join(directory(), id + '.result.json');
  fs.writeFileSync(target + '.tmp', JSON.stringify(receipt), {flag: 'wx'});
  fs.renameSync(target + '.tmp', target);
  return true;
}

function activate(context) {
  let busy = false;
  let lastStatusWrite = 0;
  async function poll() {
    if (busy) return;
    busy = true;
    const status = {version: '0.1.4', sample_time: Date.now()/1000,
      folder_count: (vscode.workspace.workspaceFolders || []).length,
      active_requests: 0, outcome: 'waiting_for_request'};
    try {
      if (!fs.existsSync(directory())) return;
      const candidates = fs.readdirSync(directory()).filter(name => /^[a-f0-9]{32}\.json$/.test(name));
      for (const name of candidates.slice(-128)) {
        const id = name.slice(0, -5);
        if (fs.existsSync(path.join(directory(), id + '.result.json'))) continue;
      try {
        readRequest(id);
        status.active_requests++;
        status.outcome = await verify(context, id) ? 'verified' : 'workspace_mismatch';
      } catch (error) {
        if (error.message !== 'expired or invalid request') {
          status.outcome = 'verification_error';
          status.error = error.code || 'invalid_request';
          console.warn('JARVIS request rejected:', error.message);
        }
      }
      }
    } finally {
      if (fs.existsSync(directory()) && Date.now() - lastStatusWrite >= 1000) {
        const target = path.join(directory(), `verifier-status-${process.pid}.json`);
        fs.writeFileSync(target + '.tmp', JSON.stringify(status));
        fs.renameSync(target + '.tmp', target);
        lastStatusWrite = Date.now();
      }
      busy = false;
    }
  }
  const report = error => console.warn('JARVIS verifier unavailable:', error.message);
  const timer = setInterval(() => poll().catch(report), 250);
  context.subscriptions.push({dispose: () => clearInterval(timer)});
  context.subscriptions.push(vscode.workspace.onDidChangeWorkspaceFolders(() => poll().catch(() => {})));
  poll().catch(report);
}

module.exports = {activate};
