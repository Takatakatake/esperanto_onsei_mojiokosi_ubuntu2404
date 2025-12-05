#!/bin/bash

###############################################################################
# git_helper.sh
#
# 目的:
#   1. よく使う Git コマンドをメニュー形式で簡単に実行する
#   2. コマンド実行をログに記録し、成功・失敗を一目でわかるようにする
#   3. スクリプトのコードを編集しやすくし、拡張や修正を容易にする
#
# 使用例:
#   $ chmod +x git_helper.sh
#   $ ./git_helper.sh
#
# カスタマイズ:
#   1. 下記の「ユーザー設定セクション」で色の設定やログファイルのパスを変更可能
#   2. 下記の「メインメニューセクション」でコマンドを自由に追加・削除可能
#
###############################################################################


###############################################################################
# ユーザー設定セクション
# (今後ここに環境設定や変数などを追加して管理しやすくします)
###############################################################################

# カラー設定 (必要に応じて変更してください)
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# ログファイルの保存先パス
LOG_FILE="$HOME/git_helper.log"


###############################################################################
# 共通関数セクション
# (ログ機能・コマンド実行機能など、どのメニューでも使う処理)
###############################################################################

# ログ関数: 実行コマンドと日時を記録
log_action() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# コマンド実行関数: 成功・失敗の表示、ログ記録をセットで行う
run_command() {
    echo -e "${BLUE}Running: $1${NC}"
    eval "$1"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Success${NC}"
        log_action "SUCCESS: $1"
    else
        echo -e "${RED}Failed${NC}"
        log_action "FAILED: $1"
    fi
}

# ヘッダ表示
show_header() {
    echo -e "${YELLOW}==============================="
    echo "       Git Helper Script"
    echo -e "===============================${NC}"
}

# メニュー表示関数
show_menu() {
    echo "1. git status"
    echo "2. git add (指定パス)"
    echo "3. git commit"
    echo "4. git push"
    echo "5. git pull (通常 or --rebase 選択可)"
    echo "6. git log"
    echo "7. git branch"
    echo "8. git checkout (指定ブランチ)"
    echo "9. git merge (指定ブランチ)"
    echo "10. git stash"
    echo "11. git remote -v"
    echo "12. git diff"
    echo "13. git stash -> git pull --rebase -> git stash pop"
    echo "14. git fetch"
    echo "15. git reset (ステージング取消 / コミット取消)"
    echo "h. Help"
    echo "0. Exit"
}

# ヘルプ表示関数
show_help() {
    echo -e "${GREEN}Git Helper Script - Help${NC}"
    echo "---------------------------------"
    echo "1. git status         : 現在のリポジトリの状態を表示"
    echo "2. git add (path)     : 指定したパスをステージング (未入力時は '.')"
    echo "3. git commit         : 単一行/マルチ行など選んでコミット"
    echo "4. git push           : リモートリポジトリに変更をプッシュ"
    echo "5. git pull           : リモートリポジトリから変更をプル (通常 or --rebase)"
    echo "6. git log            : コミット履歴を表示"
    echo "7. git branch         : ブランチ一覧を表示"
    echo "8. git checkout       : 指定したブランチに切り替え"
    echo "9. git merge          : 指定したブランチをマージ"
    echo "10. git stash         : 作業中の変更を一時保存"
    echo "11. git remote -v     : リモートリポジトリのURL等を表示"
    echo "12. git diff          : 変更内容の差分を表示"
    echo "13. git stash -> git pull --rebase -> git stash pop :"
    echo "    未コミットの変更を stash で退避し、rebase 付き pull 後に再度変更を適用"
    echo "14. git fetch         : リモートの最新状態を取得（マージはしない）"
    echo "15. git reset         : ステージング取消 or コミット取消"
    echo "h. Help               : このヘルプを表示"
    echo "0. Exit               : スクリプトを終了"
    echo "---------------------------------"
}


###############################################################################
# 個別コマンド処理セクション
# (メインループで選択された時に呼び出す具体的な処理をまとめておく)
###############################################################################

# 2. git add
git_add_path() {
    echo -n "Enter path to add (default: '.'): "
    read add_path
    # 何も入力がなかった場合は '.' を使う
    if [ -z "$add_path" ]; then
        add_path="."
    fi
    run_command "git add \"$add_path\""
}

# 3. git commit
git_commit() {
    echo "Choose commit mode:"
    echo "0) Default commit message: \"UpDaTe<datetime>\""
    echo "1) Single-line commit message"
    echo "2) Use default editor for multi-line message"
    read -p "Select commit mode [0: \"UpDaTe<datetime>\", 1: single-line, 2: multi-line] (default: 0): " commit_choice

    # デフォルトを 0 に設定 (Enter キーのみの場合)
    if [ -z "$commit_choice" ]; then
        commit_choice=0
    fi

    case $commit_choice in
        0)
            # デフォルトメッセージでコミット（日時付き）
            datetime=$(date '+%Y%m%d_%H%M%S')
            msg="UpDaTe_${datetime}"
            echo -e "${BLUE}Using default commit message: \"$msg\"${NC}"
            run_command "git commit -m \"$msg\""
            ;;
        1)
            # 単一行メッセージ。Enterだけなら日時付きUpDaTeで自動コミット
            read -p "Enter commit message (default: \"UpDaTe<datetime>\"): " msg
            if [ -z "$msg" ]; then
                datetime=$(date '+%Y%m%d_%H%M%S')
                msg="UpDaTe_${datetime}"
                echo -e "${BLUE}Using default commit message: \"$msg\"${NC}"
            fi
            run_command "git commit -m \"$msg\""
            ;;
        2)
            # エディタでのコミット (マルチ行可)
            echo -e "${BLUE}Opening editor for commit message...${NC}"
            run_command "git commit"
            ;;
        *)
            echo -e "${RED}Invalid choice for commit message. Skipped.${NC}"
            ;;
    esac
}


# ★★ ここで新しい関数を追加 ★★
git_pull_rebase_with_stash() {
    echo "Stash local changes, pull with rebase, and pop stash."

    # stashを実行
    run_command "git stash"

    # pull --rebase を実行
    run_command "git pull --rebase origin main"

    # stash pop前にstashが存在するか確認
    stash_count=$(git stash list 2>/dev/null | wc -l)
    if [ "$stash_count" -gt 0 ]; then
        run_command "git stash pop"
    else
        echo -e "${YELLOW}No stash entries to pop.${NC}"
        log_action "INFO: No stash entries to pop"
    fi
}

# git reset機能（ステージング取消 / コミット取消）
git_reset_menu() {
    echo "Choose reset mode:"
    echo "0) Unstage all files (git reset HEAD)"
    echo "1) Unstage specific file"
    echo "2) Soft reset last commit (keep changes staged)"
    echo "3) Mixed reset last commit (keep changes unstaged)"
    echo "4) Cancel"
    read -p "Select reset mode [0-4] (default: 4): " reset_choice

    if [ -z "$reset_choice" ]; then
        reset_choice=4
    fi

    case $reset_choice in
        0)
            run_command "git reset HEAD"
            ;;
        1)
            read -p "Enter file path to unstage: " file_path
            if [ -z "$file_path" ]; then
                echo -e "${RED}File path is required. Skipped.${NC}"
            else
                run_command "git reset HEAD \"$file_path\""
            fi
            ;;
        2)
            run_command "git reset --soft HEAD~1"
            ;;
        3)
            run_command "git reset --mixed HEAD~1"
            ;;
        4)
            echo -e "${YELLOW}Reset cancelled.${NC}"
            ;;
        *)
            echo -e "${RED}Invalid choice. Skipped.${NC}"
            ;;
    esac
}


###############################################################################
# メインループセクション
###############################################################################

while true; do
    show_header
    show_menu

    # ユーザーの操作入力
    read -p "Choose an option: " choice

    case $choice in
        1)
            # git status
            run_command "git status"
            ;;
        2)
            # git add (path)
            git_add_path
            ;;
        3)
            # git commit
            git_commit
            ;;
        4)
            # git push
            run_command "git push"
            ;;
        5)
            # ★ pull の方法を選択させる部分
            echo "Choose pull method:"
            echo "  0) Normal pull (default)"
            echo "  1) Pull with rebase"
            read -p "Select pull mode [0 or 1] (default: 0): " pull_choice

            if [ -z "$pull_choice" ]; then
                pull_choice=0
            fi

            case $pull_choice in
                0)
                    run_command "git pull"
                    ;;
                1)
                    run_command "git pull --rebase"
                    ;;
                *)
                    echo -e "${RED}Invalid choice for pull method. Skipped.${NC}"
                    ;;
            esac
            ;;
        6)
            # git log
            run_command "git log"
            ;;
        7)
            # git branch
            run_command "git branch"
            ;;
        8)
            # git checkout
            read -p "Enter branch name: " branch
            if [ -z "$branch" ]; then
                echo -e "${RED}Branch name is required. Skipped.${NC}"
            else
                run_command "git checkout \"$branch\""
            fi
            ;;
        9)
            # git merge
            read -p "Enter branch to merge: " merge_branch
            if [ -z "$merge_branch" ]; then
                echo -e "${RED}Branch name is required. Skipped.${NC}"
            else
                run_command "git merge \"$merge_branch\""
            fi
            ;;
        10)
            # git stash
            run_command "git stash"
            ;;
        11)
            # git remote -v
            run_command "git remote -v"
            ;;
        12)
            # git diff
            run_command "git diff"
            ;;
        13)
            # ★★★ stash -> pull --rebase -> stash pop ★★★
            git_pull_rebase_with_stash
            ;;
        14)
            # git fetch
            run_command "git fetch"
            ;;
        15)
            # git reset
            git_reset_menu
            ;;
        h|H)
            show_help
            ;;
        0)
            echo -e "${GREEN}Exiting Git Helper...${NC}"
            log_action "Exited Git Helper"
            break
            ;;
        *)
            echo -e "${RED}Invalid choice. Please try again.${NC}"
            ;;
    esac

    echo "" # 空行を挿入して見やすくする
done

