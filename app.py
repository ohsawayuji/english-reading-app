import os
import tempfile
import streamlit as st
from google import genai
from google.genai.errors import ClientError
from streamlit_mic_recorder import mic_recorder

st.set_page_config(page_title="英語音読・発音判定AI", page_icon="🎤")

st.title("🎤 英語音読・発音判定アプリ")
st.caption("即興で読んだ英文や、課題の英文を入力して音読を録音・アップロードしてみよう！")

# --- 1. APIキーの読み込み ---
api_key = st.secrets.get("GEMINI_API_KEY")

if not api_key:
    st.error("APIキーが設定されていません。StreamlitのSecretsに「GEMINI_API_KEY」を設定してください。")
    st.stop()

client = genai.Client(api_key=api_key)

# --- 2. 優先度付きモデルリストの生成 ---
@st.cache_resource
def get_candidate_models():
    available_models = [m.name for m in client.models.list()]
    model_names = [m.replace("models/", "") for m in available_models]
    
    # 優先的に使用したいモデル順序
    priority_order = [
        "gemini-2.5-flash",
        "gemini-2.0-flash", 
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-2.5-pro"
    ]
    
    # アカウントで利用可能なモデルのみ抽出
    candidates = [m for m in priority_order if m in model_names]
    
    # リストにないモデルも予備として後ろに追加
    for m in model_names:
        if m not in candidates and "gemini" in m:
            candidates.append(m)
            
    return candidates

candidate_models = get_candidate_models()

# --- 3. UIの構築 ---
st.subheader("1. 音読する英文を入力")
target_sentence = st.text_area(
    "読んだ（または読む予定の）英文を入力してください:",
    value="I like playing soccer with my friends.",
    height=100
)

st.subheader("2. 音声の準備（どちらか一方）")
tab1, tab2 = st.tabs(["🎤 ブラウザで直接録音", "📁 音声ファイルをアップロード"])

audio_bytes = None
audio_file_name = "speech.wav"

with tab1:
    st.write("下のマイクボタンを押して録音を開始し、読み終わったら再度押して停止してください。")
    audio_output = mic_recorder(
        start_prompt="🔴 録音開始",
        stop_prompt="⬛ 録音停止",
        key='recorder'
    )
    if audio_output:
        audio_bytes = audio_output['bytes']
        st.audio(audio_bytes, format='audio/wav')
        st.success("録音が完了しました！")

with tab2:
    uploaded_file = st.file_uploader("録音データ（.mp3, .wav, .m4aなど）を選択", type=["mp3", "wav", "m4a"])
    if uploaded_file is not None:
        audio_bytes = uploaded_file.read()
        audio_file_name = uploaded_file.name
        st.audio(audio_bytes)

st.divider()

# --- 4. 判定処理（フォールバック機能付き） ---
if st.button("🚀 音読を判定する", type="primary", use_container_width=True):
    if not target_sentence.strip():
        st.warning("英文を入力してください。")
    elif not audio_bytes:
        st.warning("音声データを録音するか、ファイルをアップロードしてください。")
    else:
        with st.spinner("🤖 Geminiが音声を聞いて添削中... 数秒お待ちください"):
            tmp_path = None
            audio_file = None
            
            try:
                # 一時ファイルとして音声データを保存
                ext = os.path.splitext(audio_file_name)[1]
                if not ext:
                    ext = ".wav"
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
                    tmp_file.write(audio_bytes)
                    tmp_path = tmp_file.name

                # Geminiへアップロード
                audio_file = client.files.upload(file=tmp_path)

                prompt = f"""
あなたは中学校の親しみやすい熱血英語コーチであり、発音矯正のプロフェッショナルである「Gemini先生」です。
生徒が以下の【読んだ英文】を音読しました。
添付された音声ファイルを聴き、**「ネイティブに正しく伝わるか」という厳しい基準**で評価しつつ、**生徒のやる気を引き出す温かい指導**を行ってください。

【生徒が読んだ英文】: "{target_sentence}"

---
### ⚠️ 採点・判定ルール（厳密に適用してください）

1. **日本語発音・カタカナ英語への厳しい減点**:
   - 子音の後に無駄な母音（uやoなど）を足すカタカナ発音（例: "like" を "ライク [raiku]" と発音）は、発音の正確さを**大幅に減点**してください。
   - `th` を「サ/シ」、`f/v` を「ハ/バ」、`r/l` を「ラ」で代用している場合は厳しく判定してください。
   - 強弱（ストレス）がなく、日本語特有の「平坦で一本調子な音調」になっている場合は、リズム・流暢さやイントネーションを大きく減点してください。

2. **採点基準（100点満点 / 各観点25点満点）**:
   - **90〜100点**: ネイティブに近い自然な発音・リズム・強弱（カタカナ感がほぼゼロ）。
   - **75〜89点**: カタカナ英語の癖が少し残っているが、十分通じるレベル。
   - **60〜74点**: **強いカタカナ英語・日本語発音**。単語レベルで通じにくい、または聞き取りに努力が必要な状態。
   - **60点未満**: 英文と異なる発音、または日本語読みが露骨すぎて英語として認識しづらいレベル。

3. **指導のトーン・マインド**:
   - 点数は甘くせず厳しくつけますが、言葉遣いは絶対に冷たくせず、**「まず良かったところを具体的に1つ褒める」**こと。
   - 改善点は欲張らず**最も重要な1〜2点**に絞り、カタカナ表記と簡単な口の動き（「口を横に広げて」「舌を上の歯につけて」など）でわかりやすくアドバイスしてください。

---
### 🏁 出力フォーマット（以下の形式・見出しを厳守してください）

### 🌟 今日の音読ランク: [🌟🌟🌟 (星1〜3個) / 称号: 例「クリア発音マスター」「ノリノリ・リズム名人」など]
**🎯 総合スコア: [点数]点 / 100点**
*(※カタカナ英語や日本語特有の音調が目立つ場合は、躊躇せず60〜70点台の厳しい評価にしてください)*

#### 📊 観点別評価 (各25点満点)
* **発音の正確さ [ /25点]**: （個々の単語の発音や、カタカナ発音・無駄な母音の混入がないか）
* **リズム・流暢さ [ /25点]**: （詰まりやスピード、日本語特有の平坦な音調になっていないか）
* **イントネーション [ /25点]**: （文末の上げ下げや強調、強弱のつけ方が自然か）
* **リンキング [ /25点]**: （単語と単語のつながり、音がくっついて英語らしくできているか）

#### 👏 ここが素晴らしい！ (Great Job!)
* (具体的に聞こえた良いポイントや、しっかり言えていた単語・音を1〜2点挙げて褒める)

#### 🎧 聞き取り添削 (AI Check)
* **AIが実際に聴き取った英文**: (実際に発音されていた音通りにテキスト化)

#### 🔍 カタカナ英語・日本語発音のチェック結果
* **🚨 改善が必要な単語**:
  * (例: `playing` → 実際の発音: 「プレイング [pureingu]」 / 判定: 「p」の後に「ウ」が混ざってカタカナになっている)

#### 💡 ネイティブ発音に近づくワンポイントアドバイス (Next Step)
*(※一番直したい重要な1〜2点に絞って解説)*
* **[対象の単語]**: 
  * なぜカタカナに聞こえるか: 
  * 舌・口の動かし方のコツ: 「（中学生がすぐ真似できる口や舌の動かし方）」

#### 🗣️ 先生からの応援メッセージ
(厳しい評価の理由と、「ここを直せばもっとカッコよくなるよ！」と次に向けて前向きになれるメッセージ)
"""

                response = None
                last_error = None

                # 候補モデルを順番に試行（429エラー時は次のモデルへ自動フォールバック）
                for model_name in candidate_models:
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=[audio_file, prompt]
                        )
                        break  # 成功したらループを抜ける
                    except ClientError as e:
                        if e.code == 429:
                            last_error = e
                            continue  # 429制限なら次のモデルを試す
                        raise e

                if response:
                    st.success("添削が完了しました！")
                    st.markdown(response.text)
                else:
                    st.error(f"利用可能なすべてのモデルの1日あたりの上限（無料枠）を超過しました。時間をおいて再試行してください: {last_error}")

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
            
            finally:
                # 一時ファイル・サーバー側アップロードファイルのクリーンアップ
                if audio_file:
                    try:
                        client.files.delete(name=audio_file.name)
                    except Exception:
                        pass
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)
