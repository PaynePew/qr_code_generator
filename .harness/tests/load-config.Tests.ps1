BeforeAll {
    . "$PSScriptRoot/../lib/load-config.ps1"
    $script:Fixtures = "$PSScriptRoot/fixtures"
}

Describe 'Import-HarnessConfig' {
    It 'loads a valid config and returns required keys' {
        $cfg = Import-HarnessConfig -ConfigPath "$script:Fixtures/valid-config.yml"
        $cfg.image        | Should -Be 'agent-harness:latest'
        $cfg.branch_prefix | Should -Be 'kanban-issue'
        $cfg.tracker.type | Should -Be 'github'
    }

    It 'applies default model when not specified' {
        $cfg = Import-HarnessConfig -ConfigPath "$script:Fixtures/minimal-config.yml"
        $cfg.defaults.model | Should -Be 'claude-sonnet-4-6'
    }

    It 'preserves explicit model override' {
        $cfg = Import-HarnessConfig -ConfigPath "$script:Fixtures/valid-config.yml"
        $cfg.defaults.model | Should -Be 'claude-opus-4-7'
    }

    It 'throws when image key is missing' {
        { Import-HarnessConfig -ConfigPath "$script:Fixtures/missing-image.yml" } |
            Should -Throw '*image*'
    }

    It 'throws when branch_prefix key is missing' {
        { Import-HarnessConfig -ConfigPath "$script:Fixtures/missing-branch-prefix.yml" } |
            Should -Throw '*branch_prefix*'
    }

    It 'throws when tracker.type key is missing' {
        { Import-HarnessConfig -ConfigPath "$script:Fixtures/missing-tracker-type.yml" } |
            Should -Throw '*tracker.type*'
    }

    It 'throws when tracker.type is not github' {
        { Import-HarnessConfig -ConfigPath "$script:Fixtures/invalid-tracker-type.yml" } |
            Should -Throw '*github*'
    }

    It 'throws when tracker.repo key is missing' {
        # run.ps1 calls `gh issue view --repo $cfg.tracker.repo` unconditionally;
        # surface the missing key here instead of as a confusing gh failure.
        { Import-HarnessConfig -ConfigPath "$script:Fixtures/missing-tracker-repo.yml" } |
            Should -Throw '*tracker.repo*'
    }

    It 'applies default agents.implement model and max_turns when not specified' {
        $cfg = Import-HarnessConfig -ConfigPath "$script:Fixtures/minimal-config.yml"
        $cfg.agents.implement.model     | Should -Be 'claude-sonnet-4-6'
        $cfg.agents.implement.max_turns | Should -Be '80'
    }

    It 'preserves explicit agents.implement overrides' {
        $cfg = Import-HarnessConfig -ConfigPath "$script:Fixtures/agents-config.yml"
        $cfg.agents.implement.model     | Should -Be 'claude-opus-4-7'
        $cfg.agents.implement.max_turns | Should -Be '120'
    }

    It 'applies default agents.plan model and max_turns when not specified' {
        $cfg = Import-HarnessConfig -ConfigPath "$script:Fixtures/minimal-config.yml"
        $cfg.agents.plan.model     | Should -Be 'claude-opus-4-7'
        $cfg.agents.plan.max_turns | Should -Be '10'
    }

    It 'preserves explicit agents.plan overrides' {
        $cfg = Import-HarnessConfig -ConfigPath "$script:Fixtures/agents-config.yml"
        $cfg.agents.plan.model     | Should -Be 'claude-haiku-4-5'
        $cfg.agents.plan.max_turns | Should -Be '5'
    }

    It 'rejects tab indentation' {
        $tabFile = New-TemporaryFile
        Set-Content -Path $tabFile -Value "image: foo`nbranch_prefix: bar`ntracker:`n`ttype: github" -NoNewline
        try {
            { Import-HarnessConfig -ConfigPath $tabFile } | Should -Throw '*ab*'
        } finally {
            Remove-Item $tabFile -ErrorAction SilentlyContinue
        }
    }
}
