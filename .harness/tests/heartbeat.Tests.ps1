BeforeAll {
    . "$PSScriptRoot/../lib/heartbeat.ps1"
}

Describe 'Invoke-HeartbeatReduce' {
    Context 'system init' {
        It 'resets all fields when subtype is init' {
            $state = @{ turns = 5; elapsed_s = 10; last_action = 'tool:Bash' }
            $event = @{ type = 'system'; subtype = 'init'; model = 'claude-sonnet-4-6' }
            $result = Invoke-HeartbeatReduce -State $state -Event $event
            $result.turns       | Should -Be 0
            $result.elapsed_s   | Should -Be 0
            $result.last_action | Should -Be 'init'
        }

        It 'ignores system events with a non-init subtype' {
            $state = @{ turns = 2; elapsed_s = 1; last_action = 'thinking' }
            $event = @{ type = 'system'; subtype = 'compact' }
            $result = Invoke-HeartbeatReduce -State $state -Event $event
            $result.turns       | Should -Be 2
            $result.last_action | Should -Be 'thinking'
        }
    }

    Context 'assistant content[]' {
        It 'increments turns by one per text item' {
            $state = @{ turns = 2; elapsed_s = 0; last_action = 'init' }
            $event = @{
                type    = 'assistant'
                message = @{ content = @(@{ type = 'text'; text = 'hello' }) }
            }
            $result = Invoke-HeartbeatReduce -State $state -Event $event
            $result.turns       | Should -Be 3
            $result.last_action | Should -Be 'thinking'
        }

        It 'sets last_action to tool:<name> when a tool_use item is present' {
            $state = @{ turns = 1; elapsed_s = 0; last_action = 'thinking' }
            $event = @{
                type    = 'assistant'
                message = @{ content = @(@{ type = 'tool_use'; name = 'Bash'; input = @{} }) }
            }
            $result = Invoke-HeartbeatReduce -State $state -Event $event
            $result.last_action | Should -Be 'tool:Bash'
        }

        It 'lets a tool_use override the text label when both appear in one event' {
            $state = @{ turns = 0; elapsed_s = 0; last_action = 'init' }
            $event = @{
                type    = 'assistant'
                message = @{ content = @(
                    @{ type = 'text'; text = 'reading the file' },
                    @{ type = 'tool_use'; name = 'Read'; input = @{} }
                ) }
            }
            $result = Invoke-HeartbeatReduce -State $state -Event $event
            $result.turns       | Should -Be 1
            $result.last_action | Should -Be 'tool:Read'
        }

        It 'falls back to tool:tool when name is absent' {
            $state = @{ turns = 1; elapsed_s = 0; last_action = 'thinking' }
            $event = @{
                type    = 'assistant'
                message = @{ content = @(@{ type = 'tool_use'; input = @{} }) }
            }
            $result = Invoke-HeartbeatReduce -State $state -Event $event
            $result.last_action | Should -Be 'tool:tool'
        }
    }

    Context 'result' {
        It 'derives elapsed_s by flooring duration_ms / 1000' {
            $state = @{ turns = 3; elapsed_s = 0; last_action = 'thinking' }
            $event = @{ type = 'result'; duration_ms = 42500; num_turns = 8; result = 'done' }
            $result = Invoke-HeartbeatReduce -State $state -Event $event
            $result.elapsed_s | Should -Be 42
        }

        It 'replaces turns with the authoritative num_turns from the result' {
            $state = @{ turns = 3; elapsed_s = 0; last_action = 'thinking' }
            $event = @{ type = 'result'; duration_ms = 1000; num_turns = 8 }
            $result = Invoke-HeartbeatReduce -State $state -Event $event
            $result.turns | Should -Be 8
        }

        It 'sets last_action to done' {
            $state = @{ turns = 3; elapsed_s = 0; last_action = 'thinking' }
            $event = @{ type = 'result'; duration_ms = 10000; num_turns = 4 }
            $result = Invoke-HeartbeatReduce -State $state -Event $event
            $result.last_action | Should -Be 'done'
        }
    }

    Context 'user (tool_result) and unknown' {
        It 'leaves state unchanged for user events (heartbeat only tracks the assistant side)' {
            $state = @{ turns = 4; elapsed_s = 5; last_action = 'tool:Bash' }
            $event = @{
                type    = 'user'
                message = @{ content = @(@{ type = 'tool_result'; content = 'ok' }) }
            }
            $result = Invoke-HeartbeatReduce -State $state -Event $event
            $result.turns       | Should -Be 4
            $result.last_action | Should -Be 'tool:Bash'
        }

        It 'returns state unchanged for unknown event types' {
            $state = @{ turns = 2; elapsed_s = 5.0; last_action = 'thinking' }
            $event = @{ type = 'future.unrecognised'; data = 'x' }
            $result = Invoke-HeartbeatReduce -State $state -Event $event
            $result.turns       | Should -Be 2
            $result.elapsed_s   | Should -Be 5.0
            $result.last_action | Should -Be 'thinking'
        }
    }
}
