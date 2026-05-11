BeforeAll {
    $script:RunContent = Get-Content "$PSScriptRoot/../run.ps1" -Raw
}

Describe 'run.ps1 CLI model override flags' {
    It 'declares -ImplementModel parameter' {
        $script:RunContent | Should -Match '\$ImplementModel'
    }

    It 'declares -PlanModel parameter' {
        $script:RunContent | Should -Match '\$PlanModel'
    }

    It 'declares -ReviewModel parameter' {
        $script:RunContent | Should -Match '\$ReviewModel'
    }

    It 'declares -MergeModel parameter' {
        $script:RunContent | Should -Match '\$MergeModel'
    }
}

Describe 'run.ps1 CLI max_turns override flags' {
    It 'declares -ImplementMaxTurns parameter' {
        $script:RunContent | Should -Match '\$ImplementMaxTurns'
    }

    It 'declares -PlanMaxTurns parameter' {
        $script:RunContent | Should -Match '\$PlanMaxTurns'
    }

    It 'declares -ReviewMaxTurns parameter' {
        $script:RunContent | Should -Match '\$ReviewMaxTurns'
    }

    It 'declares -MergeMaxTurns parameter' {
        $script:RunContent | Should -Match '\$MergeMaxTurns'
    }
}

Describe 'run.ps1 CLI override — precedence wiring' {
    It 'applies ImplementModel override to config after load' {
        $script:RunContent | Should -Match 'ImplementModel.*agents|agents.*ImplementModel'
    }

    It 'applies PlanModel override to config after load' {
        $script:RunContent | Should -Match 'PlanModel.*agents|agents.*PlanModel'
    }

    It 'applies ReviewModel override to config after load' {
        $script:RunContent | Should -Match 'ReviewModel.*agents|agents.*ReviewModel'
    }

    It 'applies MergeModel override to config after load' {
        $script:RunContent | Should -Match 'MergeModel.*agents|agents.*MergeModel'
    }

    It 'applies ImplementMaxTurns override to config after load' {
        $script:RunContent | Should -Match 'ImplementMaxTurns.*agents|agents.*ImplementMaxTurns'
    }

    It 'applies PlanMaxTurns override to config after load' {
        $script:RunContent | Should -Match 'PlanMaxTurns.*agents|agents.*PlanMaxTurns'
    }
}
