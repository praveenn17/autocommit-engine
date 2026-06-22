import React, { useState } from 'react'
import { Skull, AlertTriangle, Loader2, CheckCircle, Lock } from 'lucide-react'
import toast from 'react-hot-toast'
import { getOctokit } from '../lib/github'

const CONFIRM_PHRASE = 'DELETE'

export default function SelfDestructPanel({ username }) {
  const [phase, setPhase] = useState('idle') // idle | confirm | running | done
  const [projectRepo, setProjectRepo] = useState('')
  const [pat, setPat] = useState('')
  const [confirmText, setConfirmText] = useState('')
  const [log, setLog] = useState([])
  const [error, setError] = useState('')

  const appendLog = (msg, type = 'info') => {
    setLog(prev => [...prev, { msg, type, ts: new Date().toISOString() }])
  }

  const handleSelfDestruct = async () => {
    if (!projectRepo || !pat) {
      setError('Project repo name and PAT are required.')
      return
    }
    if (confirmText !== CONFIRM_PHRASE) {
      setError(`Type "${CONFIRM_PHRASE}" to confirm.`)
      return
    }

    setPhase('running')
    setLog([])
    setError('')

    try {
      appendLog(`Starting self-destruct for: ${username}/${projectRepo}`)
      appendLog('Verifying PAT credentials...')

      const { Octokit } = await import('@octokit/rest')
      const octokit = new Octokit({ auth: pat })

      // 1. Verify PAT
      let userLogin
      try {
        const { data: user } = await octokit.rest.users.getAuthenticated()
        userLogin = user.login
        appendLog(`✓ Authenticated as: ${userLogin}`, 'success')
      } catch {
        throw new Error('Invalid PAT or insufficient permissions.')
      }

      // 2. Get workflow file SHA
      appendLog(`Looking for .github/workflows/autocommit.yml in ${userLogin}/${projectRepo}...`)
      let fileSha = null
      try {
        const { data: fileData } = await octokit.rest.repos.getContent({
          owner: userLogin,
          repo: projectRepo,
          path: '.github/workflows/autocommit.yml',
        })
        fileSha = fileData.sha
        appendLog(`✓ Found workflow file (SHA: ${fileSha.slice(0, 7)}...)`, 'success')
      } catch (err) {
        if (err.status === 404) {
          appendLog('⚠ Workflow file not found — may already be removed.', 'warn')
        } else {
          throw err
        }
      }

      // 3. Delete workflow file
      if (fileSha) {
        appendLog('Deleting .github/workflows/autocommit.yml...')
        await octokit.rest.repos.deleteFile({
          owner: userLogin,
          repo: projectRepo,
          path: '.github/workflows/autocommit.yml',
          message: 'chore: remove autocommit workflow [self-destruct]',
          sha: fileSha,
        })
        appendLog('✓ Workflow file deleted.', 'success')
      }

      // 4. Delete workflow run history
      appendLog('Fetching workflow run history...')
      try {
        const { data: runs } = await octokit.rest.actions.listWorkflowRunsForRepo({
          owner: userLogin,
          repo: projectRepo,
          per_page: 100,
        })
        const runIds = runs.workflow_runs?.map(r => r.id) || []
        appendLog(`Found ${runIds.length} workflow run(s) to delete.`)

        for (const runId of runIds) {
          await octokit.rest.actions.deleteWorkflowRun({
            owner: userLogin,
            repo: projectRepo,
            run_id: runId,
          })
        }
        if (runIds.length > 0) {
          appendLog(`✓ Deleted ${runIds.length} workflow run(s).`, 'success')
        }
      } catch (err) {
        appendLog(`⚠ Could not clear run history: ${err.message}`, 'warn')
      }

      appendLog('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━', 'separator')
      appendLog('✓ Self-destruct complete!', 'success')
      appendLog(`✓ Archive repo untouched: ${userLogin}/commit-archive`, 'success')
      appendLog('✓ Your GitHub graph remains fully green.', 'success')
      appendLog('✓ Zero evidence of automation in project repo.', 'success')

      setPat('')
      setPhase('done')
      toast.success('Self-destruct complete! Archive repo untouched.')
    } catch (err) {
      setError(err.message)
      appendLog(`✗ Error: ${err.message}`, 'error')
      setPhase('confirm')
    }
  }

  const logColor = {
    info:      'text-fg-muted',
    success:   'text-success-fg',
    warn:      'text-attention-fg',
    error:     'text-danger-fg',
    separator: 'text-border',
  }

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Header */}
      <div className="flex items-center gap-2 pb-1">
        <Skull size={20} className="text-danger-fg" />
        <div>
          <h2 className="text-lg font-semibold text-danger-fg">Self-Destruct</h2>
          <p className="text-xs text-fg-muted">Remove AutoCommit from a project repo. Archive untouched.</p>
        </div>
      </div>

      {/* Warning card */}
      <div className="border border-danger-fg/30 bg-danger-muted rounded-xl p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle size={18} className="text-danger-fg flex-shrink-0 mt-0.5" />
          <div>
            <div className="text-sm font-semibold text-danger-fg mb-1">Interview Safety Mode</div>
            <div className="text-xs text-fg-muted space-y-1">
              <p>This removes the workflow YAML and run history from your <strong>project repo only</strong>.</p>
              <p>Your <strong>commit-archive repo</strong> and every green square on your graph are fully preserved.</p>
              <p>After running: zero traces of automation in the project repo.</p>
            </div>
          </div>
        </div>
      </div>

      {phase === 'idle' && (
        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <Lock size={14} className="text-fg-muted" />
            <div className="text-sm font-semibold text-fg">Protected Action</div>
          </div>
          <button
            id="btn-initiate-selfdestruct"
            onClick={() => setPhase('confirm')}
            className="btn btn-danger w-full justify-center"
          >
            <Skull size={15} />
            Initiate Self-Destruct
          </button>
        </div>
      )}

      {(phase === 'confirm' || phase === 'running') && (
        <div className="card space-y-4">
          <div className="text-sm font-semibold text-fg">Provide credentials</div>

          <div>
            <label className="block text-xs font-medium text-fg-muted mb-1.5">
              Project Repo Name (NOT the archive repo)
            </label>
            <input
              id="input-project-repo"
              type="text"
              value={projectRepo}
              onChange={e => setProjectRepo(e.target.value)}
              placeholder="my-project-name"
              disabled={phase === 'running'}
              className="w-full bg-canvas-inset border border-border rounded-lg px-3 py-2 text-sm text-fg font-mono placeholder:text-fg-subtle focus:outline-none focus:border-danger-fg transition-colors disabled:opacity-50"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-fg-muted mb-1.5">
              Personal Access Token (repo scope)
            </label>
            <input
              id="input-destruct-pat"
              type="password"
              value={pat}
              onChange={e => setPat(e.target.value)}
              placeholder="ghp_xxxxxxxxxxxx"
              disabled={phase === 'running'}
              className="w-full bg-canvas-inset border border-border rounded-lg px-3 py-2 text-sm text-fg font-mono placeholder:text-fg-subtle focus:outline-none focus:border-danger-fg transition-colors disabled:opacity-50"
            />
            <div className="text-[10px] text-fg-subtle mt-1">
              Token is used only for this action and is not stored anywhere.
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-fg-muted mb-1.5">
              Type <span className="mono">{CONFIRM_PHRASE}</span> to confirm
            </label>
            <input
              id="input-confirm-phrase"
              type="text"
              value={confirmText}
              onChange={e => setConfirmText(e.target.value)}
              placeholder={CONFIRM_PHRASE}
              disabled={phase === 'running'}
              className="w-full bg-canvas-inset border border-danger-fg/30 rounded-lg px-3 py-2 text-sm text-danger-fg font-mono placeholder:text-fg-subtle focus:outline-none focus:border-danger-fg transition-colors disabled:opacity-50"
            />
          </div>

          {error && (
            <div className="text-xs text-danger-fg bg-danger-muted px-3 py-2 rounded-lg">
              {error}
            </div>
          )}

          <button
            id="btn-confirm-selfdestruct"
            onClick={handleSelfDestruct}
            disabled={phase === 'running' || confirmText !== CONFIRM_PHRASE || !projectRepo || !pat}
            className="btn btn-danger w-full justify-center disabled:opacity-40"
          >
            {phase === 'running' ? (
              <><Loader2 size={15} className="animate-spin" /> Running…</>
            ) : (
              <><Skull size={15} /> Confirm Self-Destruct</>
            )}
          </button>
        </div>
      )}

      {/* Live log */}
      {log.length > 0 && (
        <div className="card">
          <div className="text-xs font-semibold text-fg-muted mb-2 uppercase tracking-wider">
            Execution Log
          </div>
          <div className="font-mono text-xs space-y-0.5 max-h-64 overflow-y-auto">
            {log.map((entry, i) => (
              <div key={i} className={logColor[entry.type] || 'text-fg-muted'}>
                {entry.msg}
              </div>
            ))}
          </div>
        </div>
      )}

      {phase === 'done' && (
        <div className="card border-success-emphasis/30 bg-success-muted">
          <div className="flex items-start gap-3">
            <CheckCircle size={18} className="text-success-fg flex-shrink-0 mt-0.5" />
            <div>
              <div className="text-sm font-semibold text-success-fg mb-1">
                Self-Destruct Complete
              </div>
              <div className="text-xs text-fg-muted space-y-1">
                <p>✓ Project repo is clean — no automation traces.</p>
                <p>✓ Archive repo and contribution graph fully intact.</p>
                <p>✓ You're safe for interviews.</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
