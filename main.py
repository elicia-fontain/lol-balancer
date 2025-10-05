import streamlit as st
import pandas as pd
import itertools
import requests

# --- 定数定義 ---
RIOT_API_KEY = st.secrets["RIOT_API_KEY"]

# ランク情報を一元管理
TIER_LIST = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND"]
HIGH_TIER_LIST = ["MASTER", "GRANDMASTER", "CHALLENGER"]
ALL_TIER_LIST = TIER_LIST + HIGH_TIER_LIST
RANK_LIST = ["IV", "III", "II", "I"]

# --- API関連の関数 ---

def get_api_response(base_url, endpoint, params=None):
    """APIにリクエストを送信し、JSONレスポンスを返す共通関数"""
    if params is None:
        params = {}
    # すべてのリクエストにAPIキーを付与する
    params["api_key"] = RIOT_API_KEY
    
    url = f"{base_url}{endpoint}"
    response = requests.get(url, params=params)
    response.raise_for_status()  # 200番台以外のステータスコードの場合、例外を発生させる
    return response.json()

def get_summoner_rank(game_name, tag_line):
    """Riot IDからPUUIDを取得し、そのプレイヤーのランクTierを返す"""
    # Riot IDとTaglineからスペースと見えない制御文字を削除
    # \u2066, \u2069 などがチャットのコピペで混入することがあるため
    name = "".join(char for char in game_name if char.isprintable()).strip()
    tag = "".join(char for char in tag_line if char.isprintable()).strip()
    print(f"Sanitized: '{name}'#'{tag}'")
    
    base_url_puuid = "https://asia.api.riotgames.com"
    endpoint_puuid = f"/riot/account/v1/accounts/by-riot-id/{name}/{tag}"
    account = get_api_response(base_url_puuid, endpoint_puuid, params={})
    puuid = account.get("puuid") # puuidが取得できない場合、Noneになる
    
    base_url_entry = "https://jp1.api.riotgames.com"
    endpoint_entry = f"/lol/league/v4/entries/by-puuid/{puuid}"
    
    entries = get_api_response(base_url_entry, endpoint_entry, params={})
    
    # ソロキューのランク情報を探す
    for entry in entries:
        if entry.get("queueType") == "RANKED_SOLO_5x5":
            return entry.get("tier"), entry.get("rank")
    return "UNRANKED", ""

# --- 内部ロジックの関数 ---

def get_tuyosa(tier, division):
    if tier == "UNRANKED":
        return 0
    if tier == "MASTER":
        return 2800
    if tier == "GRANDMASTER":
        return 3000
    if tier == "CHALLENGER":
        return 3100
    
    tuyosa = (ALL_TIER_LIST.index(tier)) * 400
    tuyosa += (RANK_LIST.index(division)) * 100
    return tuyosa

# --- Streamlit UI ---
# ページのタイトル
st.sidebar.title('カスタム振り分け')

st.markdown(
    """
    <style>
    textarea {
        font-size: 0.8rem !important;
        height: 50vh !important; /* 画面の高さの50%に設定 */
    }
    
    </style>
    """,
    unsafe_allow_html=True,
)

user_text = st.sidebar.text_area(
    'チャット欄をコピペしてね',
    placeholder='Hide on bush#KR1がロビーに参加しました'
)

if st.sidebar.button('追加'):
    lines = user_text.split('\n')
    participants = []
    for line in lines:
        # line（各行）に "がロビーに参加しました" という文字列が含まれているかチェック
        if '#' in line:
            # プレイヤー名だけを抽出してリストに追加
            player_name = line.replace("がロビーに参加しました。", "")
            print(player_name)
            rank = get_summoner_rank(player_name.split('#')[0], player_name.split('#')[1])
            # 重複チェック
            if player_name not in participants:
                participants.append([player_name , rank[0], rank[1]])

    # 抽出したリストをセッション状態で管理する
    st.session_state.participants = participants

edited_df = pd.DataFrame()
checked_count = 0
# セッション状態に参加者リストが存在する場合に、編集可能な表を表示
if 'participants' in st.session_state and st.session_state.participants:
    # タイトルを後から書き込むためのプレースホルダーを先に配置
    title_placeholder = st.empty()

    # ドロップダウンリスト用のランク選択肢を生成
    rank_options = ["UNRANKED"]
    for tier in TIER_LIST:
        for rank in RANK_LIST:
            rank_options.append(f"{tier} {rank}")
    rank_options.extend(HIGH_TIER_LIST)

    # 現在の参加者リストからDataFrameを作成
    df = pd.DataFrame({
        "選択": [True] * len(st.session_state.participants), # チェックボックス用の列
        "参加者": [p[0] for p in st.session_state.participants],
        "ランク": [
            p[1] if p[1] in HIGH_TIER_LIST else f"{p[1]} {p[2]}".strip()
            for p in st.session_state.participants
        ],
        "強さ" : [get_tuyosa(p[1], p[2]) for p in st.session_state.participants]
    })
    # データエディタで表を表示
    edited_df = st.data_editor(
        df,
        column_order=("選択", "参加者", "ランク"), # この順番で列を表示し、"強さ"列を隠す
        hide_index=True, # 左側のインデックスを非表示にする
        column_config={
            "選択": st.column_config.Column(
                width=40
            ),
            "参加者": st.column_config.Column(disabled=True), # 参加者名の列は編集不可にする
            "ランク": st.column_config.SelectboxColumn(
                "ランク",
                options=rank_options,
                required=True,
            ),
            "強さ": st.column_config.Column(disabled=True), # 隠した"強さ"列も編集不可に設定
        }
    )

    # ユーザーがUIでランクを変更した可能性があるので、「強さ」を再計算する
    def parse_rank(rank_str):
        parts = rank_str.split()
        if len(parts) == 2:
            return parts[0], parts[1]
        return parts[0], "" # UNRANKED, MASTERなどの場合

    # edited_dfの各行に対して新しい「強さ」を計算し、"強さ"列を更新
    edited_df['強さ'] = edited_df['ランク'].apply(lambda x: get_tuyosa(*parse_rank(x)))

    # プレースホルダーに人数を含んだタイトルを書き込む
    title_placeholder.write(f"### 参加者リスト ({edited_df['選択'].sum()} / {len(edited_df)} 人 選択中)")

    if st.button("チームを編成！"):
        # チェックボックスがTrueになっている参加者名だけを抽出
        selected_players_df = edited_df[edited_df["選択"] == True]
        players = list(selected_players_df.itertuples(index=False, name=None))

        # 参加人数が10人でない場合はエラーメッセージを表示して終了
        if len(players) != 10:
            st.error("チーム分けを行うには、10人のプレイヤーを選択してください。")
            st.stop()

        # 全プレイヤーの合計強さと、理想的なチームの強さを計算
        total_strength = sum(player[3] for player in players)
        ideal_team_strength = total_strength / 2

        best_combination = None
        min_diff = float('inf')

        # 10人から5人を選ぶ全ての組み合わせを試す
        for combination in itertools.combinations(players, 5):
            current_strength = sum(player[3] for player in combination)
            diff = abs(current_strength - ideal_team_strength)
            
            # より理想に近い組み合わせが見つかったら更新
            if diff < min_diff:
                min_diff = diff
                best_combination = combination
        # 最適なチーム分けを決定
        team_blue_players = list(best_combination)
        team_red_players = [p for p in players if p not in team_blue_players]
        team_blue_strength = sum(p[3] for p in team_blue_players)
        team_red_strength = sum(p[3] for p in team_red_players)

        # 結果をDataFrameに格納して表示
        # 階層的な列（MultiIndex）を持つDataFrameを作成
        result_df = pd.DataFrame(
            {
                ("Blue Team", "プレイヤー"): [p[1] for p in team_blue_players],
                ("Blue Team", "ランク"): [p[2] for p in team_blue_players],
                ("Red Team", "プレイヤー"): [p[1] for p in team_red_players],
                ("Red Team", "ランク"): [p[2] for p in team_red_players],
            }
        )
        # 列ヘッダーのテキストを更新
        result_df.columns = pd.MultiIndex.from_tuples([
            (f'Blue Team', 'プレイヤー'),
            (f'Blue Team', 'ランク'),
            (f'Red Team', 'プレイヤー'), (f'Red Team', 'ランク')
        ])
        st.markdown(result_df.to_html(index=False), unsafe_allow_html=True)