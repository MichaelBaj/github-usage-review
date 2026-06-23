---
id: "code-review-jenkins-groovy"
version: "1.0.0"
tags: [review, ci, jenkins, groovy, automation]
applies-to: "Jenkinsfiles/Jenkinsfile*,**/*.groovy"
---

# Code Review — Jenkins / Groovy

## Purpose

High-signal review for Jenkins pipeline and CI-oriented Groovy changes. Review changed scope
only. Focus: secret exposure, unsafe command execution, stuck or non-durable pipelines, bad
agent/workspace behavior, missing cleanup.

## Scope

- **Selectors:** `Jenkinsfile`, `*.groovy`
- **In scope:** Declarative and scripted pipelines, shared-library steps, stage orchestration, shell/process invocation, agent/workspace usage, credential binding, and pipeline options that change reliability
- **Out of scope:** General shared guidance owned by `.resources/skills/code-review.md`; non-CI Groovy business logic should fall back to generic review plus nearby context

## Shared contract

- Defer shared security, tests, docs/API compatibility, anti-patterns, and output format to `.resources/skills/code-review.md`.
- Skip formatter, lint, whitespace, naming, or import-order advice unless it hides real defect.
- Review changed lines plus directly impacted nearby context only.
- Prefer evidence-backed findings tied to concrete pipeline failure modes.

## Compact checklist

- Confirm credentials use bindings or `credentials()` indirection, stay in smallest possible scope, and never log raw secret values.
- Inspect every `sh`, `bat`, `powershell`, or `pwsh` step for unsafe interpolation, quoting bugs, and command-injection paths.
- Check `timeout`, `retry`, and `catchError` behavior so transient failures retry and hung steps fail closed.
- Verify agent labels, container/workspace reuse, and stash/unstash flow do not create cross-stage state or node-coupling bugs.
- Require reliable cleanup through `post { always { ... } }`, `finally`, or equivalent even on abort, timeout, or parallel-stage failure.
- Review shared-library calls, `load`, and dynamic step construction for hidden side effects, trust drift, and parameter validation gaps.
- Check parallel coordination, env propagation, and durability settings so long-running pipelines resume safely and do not leak state across branches.

## High-risk review areas

| Risk class | What to inspect | Merge-blocking when |
|---|---|---|
| Credential exposure | `withCredentials`, `environment`, `credentials()`, echo/log statements, shell interpolation | Secret value can print, leak into process args, persist in workspace, or remain available outside intended block |
| Command injection and quoting | String interpolation inside shell steps, parameter use, unquoted env vars, multiline scripts | User-controlled or branch-controlled data reaches shell parsing unsafely or argument splitting changes command behavior |
| Timeout and retry drift | Stage-level and step-level `timeout`, `retry`, `catchError`, backoff behavior | Pipeline can hang forever, fail flaky external calls without retry, or mask persistent failure as success |
| Agent and workspace misuse | `agent any`, `node`, `ws`, container agents, workspace sharing, stash/unstash | Stages depend on sticky workspace state, collide in parallel, or run on wrong executor/container |
| Cleanup gaps | `post` blocks, `try/finally`, lock release, temp file deletion, secret file cleanup | Abort or failed branch skips cleanup and leaves bad state, held locks, or leaked artifacts |
| Shared-library trust drift | Library step contracts, parameter validation, dynamic method names, implicit globals | Library call hides dangerous behavior, lacks validation, or broadens privilege without reviewable evidence |
| Durability and env leakage | `durabilityHint`, restart behavior, global `environment`, exported vars | Restart loses critical state, performance mode weakens required recovery, or secrets bleed into unrelated stages |

## Validation expectations

| Change shape | Expected evidence | Recommended validation |
|---|---|---|
| Jenkinsfile or shared-library control-flow change | Proof that stage order, failure handling, and post actions still behave as intended | Repo-native pipeline unit/integration test target first; fallback: Jenkins replay or job-run against representative branch/config |
| Shell step or parameter-handling change | Evidence that arguments stay quoted and hostile input cannot alter command structure | Targeted pipeline test first; fallback: run changed shell fragment with representative env and adversarial sample values |
| Credential or environment-binding change | Proof that secret values stay masked, scoped, and absent from logs/artifacts/process args | Secret-aware pipeline test first; fallback: dry run or replay with synthetic credentials and inspect console/archive surfaces |
| Agent/workspace/parallel change | Evidence that stages remain isolated, resumable, and cleanup runs after failure or abort | CI test job first; fallback: targeted run that forces branch failure, retry, and restart/resume path |
| Durability, timeout, or retry change | Proof that long-running steps fail within bounded time and transient failures recover without false green | Pipeline reliability test first; fallback: targeted replay with injected flaky command and bounded timeout |

## Deep guide (load on demand)

### Credentials and environment handling

- Prefer `withCredentials` or declarative `credentials()` over raw secret literals or manually exported env vars.
- Keep bindings inside smallest block that needs them; wide `environment` scope makes leaks and accidental reuse more likely.
- Watch for secrets passed via string interpolation into shell commands because masking usually covers logs, not process argv, files, or downstream tools.
- Strong fixes keep secret data in environment variables consumed inside quoted scripts, avoid echoing derived values, and clean secret files in `post` or `finally`.

### Shell execution and quoting

- Groovy interpolation happens before shell parsing. `sh "deploy ${params.TARGET}"` turns pipeline input into shell syntax unless arguments are tightly controlled.
- Look for branch names, PR titles, parameters, filenames, and env vars flowing into shell, PowerShell, or batch steps.
- Strong fixes validate allowed values, use quoted shell variables inside multiline scripts, and avoid concatenating optional flags into one command string.
- Validation should include hostile input samples that contain spaces, quotes, globbing, command separators, or subshell syntax.

### Timeouts, retries, and failure semantics

- Pipelines often fail by hanging forever or by retrying wrong scopes. Retry only transient operations, not whole deploy stages with side effects unless idempotence is proven.
- Check whether `catchError` downgrades hard failures into unstable/success without surfacing broken behavior.
- Strong fixes bound external calls with `timeout`, apply `retry` to narrow flaky steps, and preserve explicit failure status for persistent errors.
- Validation should force timeout and transient-failure paths, not only happy path.

### Agent, workspace, and parallel coordination

- `agent any` plus implicit workspace reuse can hide node affinity bugs, leftover artifacts, or toolchain drift.
- Parallel branches should not mutate same workspace unless intentionally synchronized; prefer `stash/unstash`, isolated containers, or explicit `ws` blocks.
- Strong fixes define required executor/container, isolate branch state, and use `failFast` or explicit aggregation when one branch invalidates whole pipeline.
- Validation should include parallel failure, aborted branch, and resumed-build behavior.

### Cleanup, libraries, and durability

- Cleanup must run on success, failure, timeout, and abort. Missing `post { always { ... } }` or `finally` causes leaked locks, temp files, and secret artifacts.
- Shared-library calls deserve same scrutiny as inline pipeline code: hidden shell steps, broad credentials, and implicit globals often move risk out of diff view.
- Review `durabilityHint` changes carefully. `PERFORMANCE_OPTIMIZED` can be wrong for long-running or hard-to-reproduce deploy flows that need resume guarantees.
- Strong fixes keep cleanup unconditional, make library contracts explicit, and use durability settings that match operational blast radius.

## Examples

### Unsafe shell interpolation with credentials

**Issue**
```groovy
withCredentials([string(credentialsId: 'deploy-token', variable: 'TOKEN')]) {
    sh "./deploy.sh --env ${params.TARGET_ENV} --token ${TOKEN} ${params.EXTRA_ARGS}"
}
```

**Fix**
```groovy
if (!(params.TARGET_ENV in ['staging', 'prod'])) {
    error("Unsupported target env: ${params.TARGET_ENV}")
}

withCredentials([string(credentialsId: 'deploy-token', variable: 'TOKEN')]) {
    withEnv(["TARGET_ENV=${params.TARGET_ENV}"]) {
        sh(label: 'Deploy', script: '''#!/usr/bin/env bash
set -euo pipefail
./deploy.sh --env "$TARGET_ENV" --token "$TOKEN"
''')
    }
}
```

**Why it matters:** Groovy interpolation and concatenated extra args let pipeline input change shell parsing and can leak secrets through process arguments. Validation should use values with spaces and shell metacharacters.

### Retry without timeout around flaky external call

**Issue**
```groovy
stage('Publish') {
    steps {
        retry(3) {
            sh 'curl -fS https://artifact.example.com/upload'
        }
    }
}
```

**Fix**
```groovy
stage('Publish') {
    steps {
        retry(3) {
            timeout(time: 2, unit: 'MINUTES') {
                sh 'curl -fS https://artifact.example.com/upload'
            }
        }
    }
}
```

**Why it matters:** Retry alone does not stop hung network calls, so executors can stall indefinitely. Validation should force timeout and transient-failure paths.

### Parallel branches sharing mutable workspace

**Issue**
```groovy
stage('Test') {
    parallel(
        linux: {
            sh 'make test-linux'
        },
        mac: {
            sh 'make test-mac'
        }
    )
}
```

**Fix**
```groovy
stage('Build') {
    steps {
        sh 'make build'
        stash name: 'workspace', includes: '**/*'
    }
}

stage('Test') {
    failFast true
    parallel(
        linux: {
            node('linux') {
                deleteDir()
                unstash 'workspace'
                sh 'make test-linux'
            }
        },
        mac: {
            node('mac') {
                deleteDir()
                unstash 'workspace'
                sh 'make test-mac'
            }
        }
    )
}
```

**Why it matters:** Parallel branches that mutate one workspace cause flaky failures and cross-node coupling. Validation should run parallel branches repeatedly and force one branch to fail.
