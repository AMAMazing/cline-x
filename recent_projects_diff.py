import os
import sys
import json
import time
import subprocess
from urllib.parse import unquote

# Fix Windows console utf-8 encoding if applicable
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# ANSI Color codes for clean standalone terminal styling
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
WHITE = "\033[37m"

def get_vscode_projects():
    """
    Finds VS Code, VS Code Insiders, and VSCodium workspace history.
    Returns directories sorted by most recently modified.
    """
    possible_paths = [
        os.path.join(os.environ.get('APPDATA', ''), 'Code', 'User', 'globalStorage', 'storage.json'),
        os.path.join(os.environ.get('APPDATA', ''), 'Code - Insiders', 'User', 'globalStorage', 'storage.json'),
        os.path.join(os.environ.get('APPDATA', ''), 'VSCodium', 'User', 'globalStorage', 'storage.json')
    ]
    
    storage_path = None
    for path in possible_paths:
        if os.path.exists(path):
            storage_path = path
            break
            
    if not storage_path:
        return []
        
    try:
        with open(storage_path, 'r', encoding='utf-8') as f:
            storage_data = json.load(f)
            
        project_uris = list(storage_data.get('profileAssociations', {}).get('workspaces', {}).keys())
        cleaned_paths = []
        for uri in project_uris:
            if uri.startswith('file:///'):
                path = unquote(uri[8:]).replace('/', '\\' if os.name == 'nt' else '/')
                cleaned_paths.append(path)
                
        folder_paths = [p for p in cleaned_paths if os.path.isdir(p)]
        return sorted(folder_paths, key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
    except Exception as e:
        print(f"{RED}[!] Error reading VS Code storage: {e}{RESET}")
        return []

def run_git_command(project_path, args):
    """Executes a git command in the target directory and returns stdout."""
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        res = subprocess.run(
            ['git'] + args,
            cwd=project_path,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=flags
        )
        return res.returncode == 0, res.stdout, res.stderr
    except FileNotFoundError:
        return False, "", "git executable not found in PATH"
    except Exception as e:
        return False, "", str(e)

def colorize_diff(diff_text):
    """Colorizes raw git diff text with terminal ANSI codes."""
    colored_lines = []
    for line in diff_text.splitlines():
        if line.startswith('+++') or line.startswith('---'):
            colored_lines.append(f"{BOLD}{WHITE}{line}{RESET}")
        elif line.startswith('+'):
            colored_lines.append(f"{GREEN}{line}{RESET}")
        elif line.startswith('-'):
            colored_lines.append(f"{RED}{line}{RESET}")
        elif line.startswith('@@'):
            colored_lines.append(f"{CYAN}{line}{RESET}")
        elif line.startswith('diff --git'):
            colored_lines.append(f"\n{BOLD}{YELLOW}{line}{RESET}")
        else:
            colored_lines.append(f"{DIM}{line}{RESET}")
    return "\n".join(colored_lines)

def main():
    total_start = time.perf_counter()
    print(f"\n{BOLD}{MAGENTA}================================================================={RESET}")
    print(f"{BOLD}{MAGENTA}      VS Code Recent Projects Git Diff & Performance Monitor     {RESET}")
    print(f"{BOLD}{MAGENTA}================================================================={RESET}\n")

    # 1. Project Discovery
    find_start = time.perf_counter()
    all_projects = get_vscode_projects()
    find_elapsed = (time.perf_counter() - find_start) * 1000 # in ms

    top_projects = all_projects[:10]
    print(f"{CYAN}[*] Found {len(all_projects)} total VS Code projects in {find_elapsed:.2f} ms.{RESET}")
    print(f"{CYAN}[*] Inspecting top {len(top_projects)} most recent projects for Git diffs...{RESET}\n")

    project_stats = []
    diff_start_total = time.perf_counter()

    for idx, proj_path in enumerate(top_projects, start=1):
        p_start = time.perf_counter()
        proj_name = os.path.basename(os.path.normpath(proj_path)) or proj_path
        
        print(f"{BOLD}{WHITE}[{idx}/{len(top_projects)}] Project: {proj_name}{RESET} {DIM}({proj_path}){RESET}")
        
        # Check if git repository
        is_git, git_check_out, _ = run_git_command(proj_path, ['rev-parse', '--is-inside-work-tree'])
        
        if not is_git:
            p_elapsed = (time.perf_counter() - p_start) * 1000
            print(f"    {YELLOW}↳ Not a git repository.{RESET} {DIM}(took {p_elapsed:.2f} ms){RESET}\n")
            project_stats.append({
                'name': proj_name,
                'is_git': False,
                'status': 'Non-Git',
                'files_changed': 0,
                'diff_lines': 0,
                'time_ms': p_elapsed
            })
            continue

        # Get status summary
        _, status_out, _ = run_git_command(proj_path, ['status', '--short'])
        modified_files = [line for line in status_out.splitlines() if line.strip()]

        # Get git diff (unstaged + staged via HEAD)
        _, diff_out, _ = run_git_command(proj_path, ['diff', 'HEAD'])
        if not diff_out.strip():
            # If no HEAD commit exists yet or no diff with HEAD, try standard git diff
            _, diff_out, _ = run_git_command(proj_path, ['diff'])

        p_elapsed = (time.perf_counter() - p_start) * 1000
        diff_lines_count = len(diff_out.splitlines()) if diff_out.strip() else 0

        if modified_files or diff_lines_count > 0:
            print(f"    {GREEN}↳ Modified Files ({len(modified_files)}):{RESET}")
            for file_line in modified_files[:15]:
                print(f"      {YELLOW}{file_line}{RESET}")
            if len(modified_files) > 15:
                print(f"      {DIM}... and {len(modified_files) - 15} more files{RESET}")
            
            if diff_out.strip():
                print(f"\n    {BOLD}Diff Preview ({diff_lines_count} lines):{RESET}")
                # Limit output if diff is enormous
                diff_preview_lines = diff_out.splitlines()[:60]
                preview_text = "\n".join(diff_preview_lines)
                print(colorize_diff(preview_text))
                if len(diff_out.splitlines()) > 60:
                    print(f"\n    {DIM}... [{len(diff_out.splitlines()) - 60} diff lines truncated for display]{RESET}")
            else:
                print(f"    {DIM}↳ Untracked or staged binary changes only.{RESET}")
        else:
            print(f"    {GREEN}↳ Working tree clean (No uncommitted diffs).{RESET}")

        print(f"    {DIM}[Processed in {p_elapsed:.2f} ms]{RESET}\n")

        project_stats.append({
            'name': proj_name,
            'is_git': True,
            'status': f"{len(modified_files)} modified" if modified_files else "Clean",
            'files_changed': len(modified_files),
            'diff_lines': diff_lines_count,
            'time_ms': p_elapsed
        })

    diff_total_elapsed = (time.perf_counter() - diff_start_total) * 1000
    total_elapsed = (time.perf_counter() - total_start) * 1000

    # 3. Performance Summary
    print(f"\n{BOLD}{MAGENTA}================================================================={RESET}")
    print(f"{BOLD}{MAGENTA}                     PERFORMANCE STATISTICS                      {RESET}")
    print(f"{BOLD}{MAGENTA}================================================================={RESET}")
    print(f" {BOLD}{'Project Name':<30} | {'Git Status':<15} | {'Diff Lines':<10} | {'Time (ms)':<10}{RESET}")
    print(f" {'-'*30}-+-{'-'*15}-+-{'-'*10}-+-{'-'*10}")
    for stat in project_stats:
        print(f" {stat['name'][:30]:<30} | {stat['status']:<15} | {stat['diff_lines']:<10} | {stat['time_ms']:<10.2f}")
    print(f" {'-'*30}-+-{'-'*15}-+-{'-'*10}-+-{'-'*10}")
    print(f"\n{BOLD}Discovery Time       :{RESET} {find_elapsed:.2f} ms")
    print(f"{BOLD}Git Processing Time  :{RESET} {diff_total_elapsed:.2f} ms")
    print(f"{BOLD}Total Execution Time :{RESET} {total_elapsed:.2f} ms")
    print(f"{BOLD}Average per Project  :{RESET} {(diff_total_elapsed / max(len(top_projects), 1)):.2f} ms")
    print(f"{BOLD}{MAGENTA}================================================================={RESET}\n")

if __name__ == '__main__':
    main()