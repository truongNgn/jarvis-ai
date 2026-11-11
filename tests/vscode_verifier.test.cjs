const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const vm = require('vm');

test('workspace API receipts bind request, path and expiry', async () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'jarvis-verifier-'));
  try {
    const directory = path.join(temp, 'JarvisAI', 'workspace-requests');
    fs.mkdirSync(directory, {recursive: true});
    const folder = path.join(temp, 'project');
    fs.mkdirSync(folder);
    const id = 'a'.repeat(32);
    const filename = path.join(directory, id + '.json');
    const request = {id, folder, project_id: 'jarvis-ai', expires: Date.now()/1000+9};
    fs.writeFileSync(filename, JSON.stringify(request));
    const vscode = {workspace: {workspaceFolders: [{uri: {scheme: 'file', fsPath: folder}}]}};
    const source = fs.readFileSync(path.join(__dirname, '../integrations/vscode-verifier/extension.js'), 'utf8');
    const functions = vm.runInNewContext(source + '; ({readRequest, verify})', {
      require: name => name === 'vscode' ? vscode : require(name), module: {exports: {}},
      process: {env: {LocalAppData: temp}}, console, URLSearchParams, setInterval, clearInterval
    });
    const context = {globalState: {update: async () => {}}};
    assert.equal(await functions.verify(context, id), true);
    const receipt = JSON.parse(fs.readFileSync(path.join(directory, id + '.result.json'), 'utf8'));
    assert.equal(receipt.id, id);
    assert.equal(receipt.method, 'vscode_workspace_api');
    vscode.workspace.workspaceFolders = [{uri: {scheme: 'file', fsPath: temp}}];
    assert.equal(await functions.verify(context, id), false);
    fs.writeFileSync(filename, JSON.stringify({...request, expires: 0}));
    assert.throws(() => functions.readRequest(id), /expired/);
    assert.throws(() => functions.readRequest('../escape'), /invalid/);
  } finally {
    fs.rmSync(temp, {recursive: true, force: true});
  }
});
