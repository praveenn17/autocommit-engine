import { Octokit } from '@octokit/rest'

// ---------------------------------------------------------------------------
// GitHub API client singleton
// ---------------------------------------------------------------------------
let _octokit = null

export function initOctokit(token) {
  _octokit = new Octokit({ auth: token })
  return _octokit
}

export function getOctokit() {
  if (!_octokit) throw new Error('Octokit not initialised. Call initOctokit first.')
  return _octokit
}

// ---------------------------------------------------------------------------
// Read a JSON file from the archive repo via GitHub Contents API
// ---------------------------------------------------------------------------
export async function readArchiveFile(owner, repo, path, token) {
  try {
    const octokit = token ? new Octokit({ auth: token }) : getOctokit()
    const { data } = await octokit.rest.repos.getContent({ owner, repo, path })
    const decoded = atob(data.content.replace(/\n/g, ''))
    return { data: JSON.parse(decoded), sha: data.sha }
  } catch (err) {
    if (err.status === 404) return { data: null, sha: null }
    throw err
  }
}

// ---------------------------------------------------------------------------
// Write a JSON file to the archive repo (creates or updates)
// ---------------------------------------------------------------------------
export async function writeArchiveFile(owner, repo, path, content, sha, message) {
  const octokit = getOctokit()
  const encoded = btoa(unescape(encodeURIComponent(JSON.stringify(content, null, 2))))
  const params = {
    owner, repo, path,
    message: message || `chore: update ${path} via dashboard`,
    content: encoded,
  }
  if (sha) params.sha = sha
  const { data } = await octokit.rest.repos.createOrUpdateFileContents(params)
  return data
}

// ---------------------------------------------------------------------------
// Load all dashboard data files in parallel
// ---------------------------------------------------------------------------
export async function loadDashboardData(owner, archiveRepo) {
  const files = [
    'commit_history.json',
    'streak_stats.json',
    'quality_score.json',
    'config.json',
  ]

  const results = await Promise.allSettled(
    files.map(f => readArchiveFile(owner, archiveRepo, f))
  )

  return {
    commitHistory:   results[0].status === 'fulfilled' ? results[0].value.data || {} : {},
    streakStats:     results[1].status === 'fulfilled' ? results[1].value.data || {} : {},
    qualityScore:    results[2].status === 'fulfilled' ? results[2].value.data || {} : {},
    config:          results[3].status === 'fulfilled' ? results[3].value.data || {} : {},
    configSha:       results[3].status === 'fulfilled' ? results[3].value.sha : null,
  }
}

// ---------------------------------------------------------------------------
// Fetch GitHub contribution graph via GraphQL API
// ---------------------------------------------------------------------------
export async function fetchContributionGraph(username, token) {
  const query = `
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
                color
              }
            }
          }
        }
      }
    }
  `

  const resp = await fetch('https://api.github.com/graphql', {
    method: 'POST',
    headers: {
      Authorization: `bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query, variables: { login: username } }),
  })

  if (!resp.ok) throw new Error(`GraphQL error: ${resp.status}`)
  const { data } = await resp.json()
  return data?.user?.contributionsCollection?.contributionCalendar || null
}

// ---------------------------------------------------------------------------
// Check if the autocommit workflow is active in project repo
// ---------------------------------------------------------------------------
export async function checkWorkflowStatus(owner, projectRepo) {
  try {
    const octokit = getOctokit()
    const { data } = await octokit.rest.actions.listWorkflowRunsForRepo({
      owner,
      repo: projectRepo,
      per_page: 1,
    })
    return data.workflow_runs?.[0] || null
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------------
// Trigger manual commit via workflow_dispatch
// ---------------------------------------------------------------------------
export async function triggerManualCommit(owner, projectRepo, workflowId = 'autocommit.yml') {
  const octokit = getOctokit()
  await octokit.rest.actions.createWorkflowDispatch({
    owner,
    repo: projectRepo,
    workflow_id: workflowId,
    ref: 'main',
    inputs: { force_commit: 'true' },
  })
}

// ---------------------------------------------------------------------------
// Verify PAT is valid and get user info
// ---------------------------------------------------------------------------
export async function verifyToken(token) {
  try {
    const octokit = new Octokit({ auth: token })
    const { data } = await octokit.rest.users.getAuthenticated()
    return { valid: true, user: data }
  } catch (err) {
    return { valid: false, error: err.message }
  }
}
