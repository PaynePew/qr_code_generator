BeforeAll {
    $script:PromptPath = "$PSScriptRoot/../prompts/review.md"
    $script:Content    = Get-Content $script:PromptPath -Raw
}

Describe 'review.md template' {
    $requiredKeys = @(
        'ISSUE', 'BRANCH', 'TARGET_BRANCH',
        'DOCS_CONTEXT', 'DOCS_ADR_DIR', 'CODING_STANDARDS_BLOCK'
    )

    It "contains placeholder {{<key>}} for each required substitution key" -ForEach ($requiredKeys | ForEach-Object { @{ Key = $_ } }) {
        $script:Content | Should -Match ([regex]::Escape("{{$($_.Key)}}"))
    }

    It 'bakes in universal rubric: no as any / @ts-ignore' {
        $script:Content | Should -Match 'as any|@ts-ignore'
    }

    It 'bakes in universal rubric: no swallowed errors' {
        $script:Content | Should -Match 'swallow'
    }

    It 'bakes in universal rubric: no nested ternaries' {
        $script:Content | Should -Match 'ternari'
    }

    It 'enforces correctness before clarity' {
        $script:Content | Should -Match '[Cc]orrectness'
    }

    It 'enforces refactor: commit prefix' {
        $script:Content | Should -Match 'refactor:'
    }

    It 'instructs posting a structured comment via gh issue comment' {
        $script:Content | Should -Match 'gh issue comment'
    }

    It 'structured comment covers Changes made' {
        $script:Content | Should -Match 'Changes made'
    }

    It 'structured comment covers Concerns flagged for human' {
        $script:Content | Should -Match 'Concerns flagged'
    }

    It 'structured comment covers Test results' {
        $script:Content | Should -Match 'Test results'
    }

    It 'structured comment covers Standards drift' {
        $script:Content | Should -Match 'Standards drift'
    }

    It 'includes promise-COMPLETE exit marker' {
        $script:Content | Should -Match ([regex]::Escape('<promise>COMPLETE'))
    }

    It 'forbids modifying TARGET_BRANCH or pushing' {
        $script:Content | Should -Match 'NOT.*push|push.*NOT|do not push|Do NOT push'
    }
}
