"""Exercise the sync with real local Git histories; only GitHub PR calls are stubbed."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'sync_bn_upstream.py'
FAKE_GH = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
from urllib.parse import parse_qs
a = sys.argv[1:]
p = Path(os.environ['FAKE_GH_STATE'])
s = json.loads(p.read_text())
def value(flag): return a[a.index(flag) + 1]
if a[0] == 'api':
    q = parse_qs(a[1].split('?', 1)[1])
    matches = [x for x in s if x['base'] == q['base'][0] and x['head'] == q['head'][0]]
    print(matches[0]['number'] if matches else '')
elif a[:2] == ['pr', 'list']:
    matches = [x for x in s if x['base'] == value('--base') and x['head'] == value('--head')]
    print(matches[0]['number'] if matches else '')
elif a[:2] == ['pr', 'create']:
    n = str(len(s) + 1)
    s.append(dict(number=n, base=value('--base'), head=value('--head'),
                  body=Path(value('--body-file')).read_text()))
    print('https://github.example/owner/fork/pull/' + n)
elif a[:2] == ['pr', 'edit']:
    next(x for x in s if x['number'] == a[2])['body'] = Path(value('--body-file')).read_text()
else:
    raise AssertionError(a)
p.write_text(json.dumps(s))
'''


class UpstreamSyncTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='bn-sync-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.origin = self.root / 'origin.git'
        self.upstream = self.root / 'upstream.git'
        self.seed = self.root / 'seed'
        self.git(self.root, 'init', '--bare', str(self.origin))
        self.git(self.root, 'init', '--bare', str(self.upstream))
        self.git(self.root, 'init', '-b', 'master', str(self.seed))
        self.commit(self.seed, 'common.txt', 'original\n')
        self.git(self.seed, 'remote', 'add', 'origin', str(self.origin))
        self.git(self.seed, 'push', 'origin', 'master')
        self.git(self.seed, 'push', str(self.upstream), 'master')
        self.git(self.seed, 'checkout', '-b', 'ultica-bn')
        self.commit(self.seed, 'bn.txt', 'BN changes\n')
        self.git(self.seed, 'push', 'origin', 'ultica-bn')
        self.base = self.git(self.origin, 'rev-parse', 'ultica-bn')
        self.worker = self.root / 'worker'
        self.upstream_work = self.root / 'upstream-work'
        self.git(self.root, 'clone', '-b', 'ultica-bn', str(self.origin), str(self.worker))
        self.git(self.root, 'clone', '-b', 'master', str(self.upstream), str(self.upstream_work))
        binary = self.root / 'bin'
        binary.mkdir()
        (binary / 'gh').write_text(FAKE_GH)
        (binary / 'gh').chmod(0o755)
        self.state = self.root / 'prs.json'
        self.state.write_text('[]')
        self.plan_path = self.root / 'plan.json'
        self.env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'],
                        FAKE_GH_STATE=str(self.state), GITHUB_REPOSITORY='owner/fork',
                        SYNC_UPSTREAM=str(self.upstream), SYNC_RUN_ID='100-1',
                        SYNC_UPSTREAM_HEAD='upstream:master',
                        SYNC_RUN_URL='https://github.example/run/100')
        self.env.pop('GITHUB_OUTPUT', None)

    def git(self, directory, *args):
        result = subprocess.run(['git', '-C', str(directory), *args], text=True,
                                capture_output=True, check=True)
        return result.stdout.strip()

    def commit(self, directory, filename, text):
        (directory / filename).write_text(text)
        self.git(directory, 'add', filename)
        self.git(directory, '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                 'commit', '-m', filename)
        return self.git(directory, 'rev-parse', 'HEAD')

    def advance_upstream(self, filename='upstream.txt', text='new upstream artwork\n'):
        sha = self.commit(self.upstream_work, filename, text)
        self.git(self.upstream_work, 'push', 'origin', 'master')
        return sha

    def prepare(self, code=0):
        result = subprocess.run([sys.executable, str(SCRIPT), 'prepare', '--output',
                                 str(self.plan_path)], cwd=self.worker, env=self.env,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, code, result.stderr)
        return json.loads(self.plan_path.read_text())

    def finish(self, plan, result='success', code=0):
        done = subprocess.run([sys.executable, str(SCRIPT), 'finish'], cwd=self.worker,
                              env=self.env | {'SYNC_PLAN': json.dumps(plan),
                                              'SYNC_BUILD_RESULT': result},
                              text=True, capture_output=True)
        self.assertEqual(done.returncode, code, done.stderr)

    def prs(self):
        return json.loads(self.state.read_text())

    def test_success_promotes_exact_checked_merge_and_preserves_bn(self):
        upstream = self.advance_upstream()
        plan = self.prepare()
        self.assertEqual(self.git(self.origin, 'rev-parse', 'master'), upstream)
        self.assertEqual(self.git(self.origin, 'rev-parse', 'ultica-bn'), self.base)
        self.assertEqual(plan['ready'], 'true')
        self.finish(plan)
        self.assertEqual(self.git(self.origin, 'rev-parse', 'ultica-bn'), plan['candidate_sha'])
        self.assertEqual(self.git(self.origin, 'show', 'ultica-bn:bn.txt'), 'BN changes')
        self.assertEqual(self.git(self.origin, 'show', 'ultica-bn:upstream.txt'), 'new upstream artwork')
        self.assertIn('All BN tilesets passed', self.prs()[0]['body'])
        self.assertNotIn(plan['candidate_ref'], self.git(self.origin, 'branch', '--list'))

    def test_no_new_upstream_does_not_create_a_pr_or_candidate(self):
        plan = self.prepare()
        self.assertEqual(plan['ready'], 'false')
        self.assertEqual(self.prs(), [])
        self.assertEqual(self.git(self.origin, 'rev-parse', 'ultica-bn'), self.base)
        self.assertNotIn('sync/', self.git(self.origin, 'branch', '--list'))

    def test_conflict_leaves_pr_and_preserves_bn(self):
        self.git(self.seed, 'checkout', 'ultica-bn')
        self.base = self.commit(self.seed, 'common.txt', 'BN version\n')
        self.git(self.seed, 'push', 'origin', 'ultica-bn')
        self.advance_upstream('common.txt', 'upstream version\n')
        plan = self.prepare(code=1)
        self.assertEqual(plan['ready'], 'false')
        self.assertEqual(self.git(self.origin, 'rev-parse', 'ultica-bn'), self.base)
        self.assertEqual(self.prs()[0]['base'], 'ultica-bn')
        self.assertIn('common.txt', self.prs()[0]['body'])

    def test_failed_or_cancelled_build_never_promotes(self):
        self.advance_upstream()
        plan = self.prepare()
        for result in ('failure', 'cancelled', 'skipped'):
            with self.subTest(result=result):
                self.finish(plan, result=result)
                self.assertEqual(self.git(self.origin, 'rev-parse', 'ultica-bn'), self.base)
                self.assertIn(result, self.prs()[0]['body'])
                self.assertIn(plan['candidate_ref'], self.git(self.origin, 'branch', '--list'))

    def test_concurrent_bn_change_is_not_overwritten(self):
        self.advance_upstream()
        plan = self.prepare()
        self.git(self.seed, 'checkout', 'ultica-bn')
        changed = self.commit(self.seed, 'bn.txt', 'new user changes\n')
        self.git(self.seed, 'push', 'origin', 'ultica-bn')
        self.finish(plan, code=1)
        self.assertEqual(self.git(self.origin, 'rev-parse', 'ultica-bn'), changed)
        self.assertIn('not promoted', self.prs()[0]['body'])

    def test_diverged_master_is_not_reset(self):
        self.git(self.seed, 'checkout', 'master')
        master = self.commit(self.seed, 'local-master.txt', 'keep this\n')
        self.git(self.seed, 'push', 'origin', 'master')
        self.advance_upstream()
        plan = self.prepare(code=1)
        self.assertEqual(plan['ready'], 'false')
        self.assertEqual(self.git(self.origin, 'rev-parse', 'master'), master)
        self.assertEqual(self.prs()[0]['base'], 'master')

    def test_changed_candidate_is_rejected(self):
        self.advance_upstream()
        plan = self.prepare()
        changed = self.commit(self.worker, 'unexpected.txt', 'not checked\n')
        self.git(self.worker, 'push', 'origin', f"HEAD:refs/heads/{plan['candidate_ref']}")
        self.finish(plan, code=1)
        self.assertEqual(self.git(self.origin, 'rev-parse', 'ultica-bn'), self.base)
        self.assertNotEqual(changed, plan['candidate_sha'])
        self.assertIn('changed after preparation', self.prs()[0]['body'])

    def test_rejected_pushes_leave_a_cross_fork_pr(self):
        self.advance_upstream()
        hook = self.origin / 'hooks' / 'pre-receive'
        hook.write_text('#!/bin/sh\necho "workflow permission denied" >&2\nexit 1\n')
        hook.chmod(0o755)
        for _ in range(2):
            plan = self.prepare(code=1)
            self.assertEqual(plan['ready'], 'false')
            self.assertEqual(self.git(self.origin, 'rev-parse', 'ultica-bn'), self.base)
            self.assertEqual(len(self.prs()), 1)
            self.assertEqual(self.prs()[0]['head'], 'upstream:master')
            self.assertIn('workflow permission denied', self.prs()[0]['body'])

    def test_rejected_candidate_push_updates_the_pr(self):
        self.advance_upstream()
        hook = self.origin / 'hooks' / 'pre-receive'
        hook.write_text('#!/bin/sh\nwhile read old new ref; do\n'
                        'case "$ref" in refs/heads/sync/check-*) exit 1;; esac\ndone\n')
        hook.chmod(0o755)
        plan = self.prepare(code=1)
        self.assertEqual(plan['ready'], 'false')
        self.assertEqual(self.git(self.origin, 'rev-parse', 'ultica-bn'), self.base)
        self.assertIn('Publishing the merge failed', self.prs()[0]['body'])

    def test_new_attempt_updates_the_existing_pr(self):
        self.advance_upstream()
        first = self.prepare()
        self.finish(first, result='failure')
        self.advance_upstream('upstream.txt', 'next update\n')
        self.env['SYNC_RUN_ID'] = '101-1'
        second = self.prepare()
        self.assertEqual(first['pr'], second['pr'])
        self.assertEqual(len(self.prs()), 1)
        self.finish(second)
        self.assertEqual(self.git(self.origin, 'rev-parse', 'ultica-bn'), second['candidate_sha'])

    def test_manually_changed_incoming_branch_is_preserved(self):
        self.git(self.seed, 'checkout', '-b', 'sync/upstream', 'master')
        manual = self.commit(self.seed, 'manual.txt', 'keep this branch\n')
        self.git(self.seed, 'push', 'origin', 'sync/upstream')
        upstream = self.advance_upstream()
        plan = self.prepare()
        self.assertEqual(plan['incoming'], f'sync/upstream-{upstream[:12]}')
        self.assertEqual(self.git(self.origin, 'rev-parse', 'sync/upstream'), manual)
        self.finish(plan)
        self.assertEqual(self.git(self.origin, 'rev-parse', 'ultica-bn'), plan['candidate_sha'])

    def test_unrelated_candidate_commit_is_rejected_even_with_a_matching_ref(self):
        self.advance_upstream()
        plan = self.prepare()
        plan['candidate_sha'] = self.commit(self.worker, 'unexpected.txt', 'not a merge\n')
        self.git(self.worker, 'push', 'origin', f"HEAD:refs/heads/{plan['candidate_ref']}")
        self.finish(plan, code=1)
        self.assertEqual(self.git(self.origin, 'rev-parse', 'ultica-bn'), self.base)
        self.assertIn('not the prepared merge', self.prs()[0]['body'])


if __name__ == '__main__':
    unittest.main()
