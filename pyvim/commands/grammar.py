from prompt_toolkit.contrib.regular_languages.compiler import compile

from .commands import get_commands_taking_locations

#: The compiled grammar for the Vim command line.
COMMAND_GRAMMAR = compile(
    r"""
    # Allow leading colons and whitespace. (They are ignored.)
    :*
    \s*
    (
        # Substitute command
        ((?P<range_start>\d+)(,(?P<range_end>\d+))?)?  (?P<command>s|substitute) \s* / (?P<search>[^/]*) ( / (?P<replace>[^/]*) (?P<flags> /(g)? )? )?   |

        # Commands accepting a location.
        (?P<command>%(commands_taking_locations)s)(?P<force>!?)  \s+   (?P<location>[^\s]+)   |

        # Commands accepting a buffer.
        (?P<command>b|buffer)(?P<force>!?)  \s+   (?P<buffer_name>[^\s]+)    |

        # Jump to line numbers.
        (?P<go_to_line>\d+)                                     |

        # Set operation
        (?P<command>set) \s+ (?P<set_option>[^\s=]+)
                             (=(?P<set_value>[^\s]+))?           |

        # Colorscheme command
        (?P<command>colorscheme|colo) \s+ (?P<colorscheme>[^\s]+)    |

        # Shell command
        !(?P<shell_command>.*)                                  |

        # Any other normal command.
        (?P<command>[^\s!]+)(?P<force>!?)                         |

        # Accept the empty input as well. (Ignores everything.)

        #(?P<command>colorscheme.+)    (?P<colorscheme>[^\s]+)  |
    )

    # Allow trailing space.
    \s*
"""
    % {
        # `sorted` keeps the regex alternation deterministic between runs
        # (docs/bugs/009.md); a set's iteration order changes per interpreter.
        'commands_taking_locations': '|'.join(sorted(get_commands_taking_locations())),
    }
)
