"""Prepare an upstream merge, then promote only the commit checked by CI."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def run(*args, check=True):
    result = subprocess.run(args, text=True, capture_output=True)
    if check and result.returncode:
        raise RuntimeError(f"{args[0]} failed: {result.stderr.strip()}")
    return result


def git(*args):
    return run('git', *args).stdout.strip()


def update_pr(repo, head, base, body):
    with tempfile.TemporaryDirectory(prefix='bn-sync-pr-') as temporary:
        path = Path(temporary) / 'body.md'
        path.write_text(body, encoding='utf-8')
        if ':' in head:
            # gh pr list does not support owner:branch in --head.
            number = run('gh', 'api', f'repos/{repo}/pulls?base={base}&head={head}&state=open',
                         '--jq', '.[0].number // empty').stdout.strip()
        else:
            number = run('gh', 'pr', 'list', '--repo', repo, '--base', base,
                         '--head', head, '--state', 'open', '--json', 'number',
                         '--jq', '.[0].number // empty').stdout.strip()
        if number:
            run('gh', 'pr', 'edit', number, '--repo', repo, '--body-file', str(path))
            return number
        url = run('gh', 'pr', 'create', '--repo', repo, '--base', base,
                  '--head', head, '--title', f'Sync upstream into {base}',
                  '--body-file', str(path)).stdout.strip()
        return url.rstrip('/').split('/')[-1]


def body(plan, message):
    return (f"{message}\n\n"
            f"Upstream: `{plan['upstream_sha']}`\n"
            f"BN base: `{plan['base_sha']}`\n\n"
            f"[Checks and build logs]({plan['run_url']})\n")


def incoming_branch(sha):
    for branch in ('sync/upstream', f'sync/upstream-{sha[:12]}'):
        if not run('git', 'push', 'origin', f'{sha}:refs/heads/{branch}',
                   check=False).returncode:
            return branch
    # Use an upstream PR when workflow-file permissions block the push.
    return os.environ['SYNC_UPSTREAM_HEAD']


def prepare(repo, upstream, run_id):
    plan = {'ready': 'false', 'run_url': os.environ.get('SYNC_RUN_URL', '')}
    git('fetch', '--no-tags', upstream, 'master')
    plan['upstream_sha'] = git('rev-parse', 'FETCH_HEAD')
    git('fetch', '--no-tags', 'origin',
        '+refs/heads/master:refs/remotes/origin/master',
        '+refs/heads/ultica-bn:refs/remotes/origin/ultica-bn')
    plan['base_sha'] = git('rev-parse', 'origin/ultica-bn')
    mirrored = run('git', 'push', 'origin',
                   f"{plan['upstream_sha']}:refs/heads/master", check=False)
    if mirrored.returncode:
        incoming = incoming_branch(plan['upstream_sha'])
        plan['incoming'] = incoming
        plan['pr'] = update_pr(repo, incoming, 'master', body(
            plan, 'The mirror update was rejected. Please resolve it manually.\n\n' +
            mirrored.stderr.strip()))
        return plan, 1
    if not run('git', 'merge-base', '--is-ancestor', plan['upstream_sha'],
               plan['base_sha'], check=False).returncode:
        return plan, 0

    incoming = incoming_branch(plan['upstream_sha'])
    plan['incoming'] = incoming
    plan['pr'] = update_pr(repo, incoming, 'ultica-bn', body(
        plan, 'Preparing an upstream merge. All BN tilesets must build before promotion.'))
    git('checkout', '--detach', plan['base_sha'])
    merged = run('git', '-c', 'user.name=github-actions[bot]', '-c',
                 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                 'merge', '--no-ff', '--no-edit', plan['upstream_sha'], check=False)
    if merged.returncode:
        conflicts = git('diff', '--name-only', '--diff-filter=U')
        git('merge', '--abort')
        update_pr(repo, incoming, 'ultica-bn', body(
            plan, 'The merge has conflicts. Resolve them manually.\n\n' +
            '\n'.join(f'- `{path}`' for path in conflicts.splitlines())))
        return plan, 1
    plan['candidate_sha'] = git('rev-parse', 'HEAD')
    plan['candidate_ref'] = f'sync/check-{run_id}'
    published = run('git', 'push', 'origin', f"HEAD:refs/heads/{plan['candidate_ref']}",
                    check=False)
    if published.returncode:
        update_pr(repo, incoming, 'ultica-bn', body(
            plan, 'Publishing the merge failed. The BN branch was not updated.\n\n' +
            published.stderr.strip()))
        return plan, 1
    plan['ready'] = 'true'
    return plan, 0


def finish(repo, plan, result):
    if result != 'success':
        update_pr(repo, plan['incoming'], 'ultica-bn', body(
            plan, f'Checks or a tileset build did not succeed ({result}). '
            'The BN branch was not updated. Please review the logs.'))
        return False
    for key in ('base_sha', 'upstream_sha', 'candidate_sha'):
        if not re.fullmatch('[0-9a-f]{40}', plan[key]):
            raise ValueError(f'Invalid {key}')
    git('fetch', '--no-tags', 'origin', plan['candidate_ref'])
    if git('rev-parse', 'FETCH_HEAD') != plan['candidate_sha']:
        raise RuntimeError('The candidate branch changed after preparation')
    parents = git('rev-list', '--parents', '-n', '1', plan['candidate_sha']).split()
    if parents != [plan['candidate_sha'], plan['base_sha'], plan['upstream_sha']]:
        raise RuntimeError('The candidate is not the prepared merge')
    # Reject concurrent changes to the tested base.
    promoted = run('git', 'push',
                   f"--force-with-lease=refs/heads/ultica-bn:{plan['base_sha']}",
                   'origin', f"{plan['candidate_sha']}:refs/heads/ultica-bn", check=False)
    if promoted.returncode:
        update_pr(repo, plan['incoming'], 'ultica-bn', body(
            plan, 'The BN branch changed or rejected the update. '
            'The checked merge was not promoted. Please review or rerun the sync.'))
        return False
    update_pr_number(repo, plan['pr'], body(
        plan, f"All BN tilesets passed. Merged as `{plan['candidate_sha']}`."))
    git('push', 'origin', '--delete', plan['candidate_ref'])
    return True


def update_pr_number(repo, number, text):
    with tempfile.TemporaryDirectory(prefix='bn-sync-pr-') as temporary:
        path = Path(temporary) / 'body.md'
        path.write_text(text, encoding='utf-8')
        run('gh', 'pr', 'edit', str(number), '--repo', repo, '--body-file', str(path))


def outputs(values):
    if path := os.environ.get('GITHUB_OUTPUT'):
        with open(path, 'a', encoding='utf-8') as stream:
            for key, value in values.items():
                if '\n' in str(value):
                    raise ValueError('Multiline workflow output')
                stream.write(f'{key}={value}\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'finish'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    repo = os.environ['GITHUB_REPOSITORY']
    if args.phase == 'prepare':
        run_id = os.environ['SYNC_RUN_ID']
        if not re.fullmatch('[0-9]+-[0-9]+', run_id):
            raise ValueError('Invalid run ID')
        plan, code = prepare(repo, os.environ['SYNC_UPSTREAM'], run_id)
        if args.output:
            args.output.write_text(json.dumps(plan), encoding='utf-8')
        outputs(plan)
        return code
    plan = json.loads(os.environ['SYNC_PLAN'])
    try:
        promoted = finish(repo, plan, os.environ['SYNC_BUILD_RESULT'])
    except (RuntimeError, ValueError) as error:
        update_pr_number(repo, plan['pr'], body(
            plan, f'Promotion stopped: {error}. The PR needs manual review.'))
        raise
    outputs({'promoted': str(promoted).lower()})
    return 0 if promoted or os.environ['SYNC_BUILD_RESULT'] != 'success' else 1


if __name__ == '__main__':
    raise SystemExit(main())
