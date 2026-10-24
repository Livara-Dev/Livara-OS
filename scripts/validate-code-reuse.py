#!/usr/bin/env python3
"""Accept a same-repository compiled candidate only when build inputs match.

A failed native smoke does not discard successful compilation. Reuse still
requires a fresh runtime test and strict archive/source manifest validation.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BUILD_INPUTS = ('forks/code', 'build/Dockerfile.code', 'scripts/build-code.sh',
                'scripts/docker-local.sh', 'scripts/prepare-code-headers.py',
                'scripts/build-fonts.py', 'fonts', 'artwork/livara-code.png')


def matching_inputs(previous, current, root=ROOT):
    result = subprocess.run(['git', 'diff', '--quiet', previous, current, '--', *BUILD_INPUTS], cwd=root)
    if result.returncode not in (0, 1):
        raise ValueError('Unable to compare candidate source inputs')
    return result.returncode == 0


def candidate_run(run, jobs, repository):
    if run.get('head_repository', {}).get('full_name') != repository:
        raise ValueError('Candidate must come from the same repository')
    revision = run.get('head_sha', '')
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Candidate source revision is invalid')
    if not any(any(step.get('name') == 'Compile actual pinned Code source' and step.get('conclusion') == 'success'
                   for step in job.get('steps', [])) and
               any(step.get('name') == 'Preserve compiled candidate before runtime testing' and step.get('conclusion') == 'success'
                   for step in job.get('steps', [])) for job in jobs):
        raise ValueError('Source run did not successfully compile and preserve a Code candidate')
    return revision


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', path], text=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch('[0-9]+', args.run_id):
        parser.error('Reuse run ID must be numeric')
    repository = os.environ['GITHUB_REPOSITORY']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Unexpected repository identity')
    run = api(f'repos/{repository}/actions/runs/{args.run_id}')
    jobs = api(f'repos/{repository}/actions/runs/{args.run_id}/jobs?per_page=100')['jobs']
    previous = candidate_run(run, jobs, repository)
    subprocess.run(['git', 'cat-file', '-e', previous + '^{commit}'], cwd=ROOT, check=True)
    reuse = matching_inputs(previous, os.environ['GITHUB_SHA'])
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write('reuse=' + ('true' if reuse else 'false') + '\n')
    record = {'candidate_run_id': args.run_id, 'candidate_source_commit': previous,
              'current_source_commit': os.environ['GITHUB_SHA'], 'build_inputs_match': reuse}
    (ROOT / '.build').mkdir(exist_ok=True)
    (ROOT / '.build/code-reuse.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Compiled Code candidate build inputs match; fresh runtime validation required.' if reuse
          else 'Code build inputs changed; compiling a fresh candidate instead.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
