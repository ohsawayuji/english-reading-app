import os
import tempfile
import streamlit as st
from google import genai
from streamlit_mic_recorder import mic_recorder

st.set_page_config(page_title="英語音読・発音判定AI", page_icon="🎤")

st.title("🎤 英語音読・発音判定アプリ")
st.caption("即興で読んだ英文や、課題の英文を入力して音読を録音・アップロードしてみよう！")

# --- 1. APIキーの読み込み ---
# Streamlit SecretsからAPIキーを取得
api_key = st.secrets.get("GEMINI_API_KEY")

if not api_key:
    st.error("APIキーが設定されていません。StreamlitのSecretsに「GEMINI_API_KEY」を設定してください。")
    st.stop()

# クライアント初期化
client = genai.Client(api_key=api_key)

# --- 2. モデルの自動選択 ---
@st.cache_resource
def get_target_model():
    available_models = [m.name for m in client.models.list()]
    model_names = [m.replace("models/", "") for m in available_models]
    
    for priority_model in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]:
        if priority_model in model_names:
            return priority_model
    return model_names[0]

target_model = get_target_model()

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

# --- 4. 判定処理 ---
if st.button("🚀 音読を判定する", type="primary", use_container_width=True):
    if not target_sentence.strip():
        st.warning("英文を入力してください。")
    elif not audio_bytes:
        st.warning("音声データを録音するか、ファイルをアップロードしてください。")
    else:
        with st.spinner("🤖 Geminiが音声を聞いて添削中... 数秒お待ちください"):
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
あなたは日本の中学生向け英語音読コーチです。
生徒が以下の【読んだ英文】を音読しました。
添付された音声ファイルを注意深く聴き、正しく読めているか照合・評価を行ってください。

【生徒が読んだ英文】: "{target_sentence}"

音声の「発音」「リズム」「イントネーション」「リンキング（音のつながり）」を細かく聞き取り、
以下のフォーマットで中学生に優しくわかりやすく回答してください。

### 🎯 総合スコア: [100点満点で点数]

#### 📊 観点別評価 (各25点満点)
*   **発音の正確さ**: （個々の単語の発音や、指定テキスト通りに読めているか）
*   **リズム・流暢さ**: （詰まりやスピード、自然なポーズの有無）
*   **イントネーション**: （文末の上げ下げや強調、抑揚のつき方）
*   **リンキング**: （単語と単語のつながり、音がくっついているか）

#### 📝 聞き取り添削
*   **AIが実際に聞き取った英文**: （実際にどう発音されたかテキスト化）
*   **🌟 良かったところ**: （上手に発音できている単語や滑らかな部分）
*   **⚠️ 改善が必要な単語・表現**: （読み飛ばした単語、言い間違えた箇所、カタカナ英語っぽい発音の修正指導）

#### 👨‍🏫 先生からのアドバイス
（次もっと良くするための具体的で実践的なアドバイス）
"""

                response = client.models.generate_content(
                    model=target_model,
                    contents=[audio_file, prompt]
                )

                # クリーンアップ
                client.files.delete(name=audio_file.name)
                os.remove(tmp_path)

                st.success("添削が完了しました！")
                st.markdown(response.text)

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")