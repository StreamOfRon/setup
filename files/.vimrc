set nocp
syntax enable

set smarttab
set shiftwidth=2
set tabstop=2

set ai
set si
set wrap

set showmatch
set mat=2

set incsearch
set hlsearch
set smartcase
set ignorecase

set autoread
filetype plugin on
filetype indent on

set nobackup
set nowb
set noswapfile

set encoding=utf8

" Disable modelines: bundled indent scripts (e.g. indent/json.vim) end with a
" modeline like "vim:set ... ts=8 noet:" which, when sourced, clobbers the
" buffer's tab settings with an 8-wide non-expanded tab for JSON files.
set nomodeline

" JSON: use expanded 2-space indentation instead of the bundled 8-space tabs.
augroup json_indent
  autocmd!
  autocmd FileType json,jsonc setlocal expandtab tabstop=2 shiftwidth=2 softtabstop=2
augroup END
