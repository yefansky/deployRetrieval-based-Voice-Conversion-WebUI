import os
import subprocess
import requests
import zipfile
import sys
import shutil
import threading
import queue
import time

# 设置工作目录和项目相关信息
PROJECT_DIR = "Retrieval-based-Voice-Conversion-WebUI"
GIT_URL = "https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI.git"
VENV_DIR = "RBVC"
FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
PYTHON_VERSION = "3.10.11"
PYTHON_INSTALLER_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-amd64.exe"
PYTHON_CMD = "py -3.10"

def run_command(command, description, check=True, timeout=60000):
    """运行 shell 命令，实时输出 stdout 和 stderr，并返回结果，支持超时"""
    print(f"{description}... (命令: {command})")
    
    # 设置环境变量以强制无缓冲输出
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    
    # 启动子进程
    process = subprocess.Popen(
        command,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env
    )
    
    # 使用队列收集输出
    stdout_queue = queue.Queue()
    stderr_queue = queue.Queue()
    
    # 定义读取线程
    def read_output(pipe, q):
        while True:
            line = pipe.readline()
            if not line and process.poll() is not None:
                break
            if line:
                q.put(line)
    
    # 启动读取线程
    stdout_thread = threading.Thread(target=read_output, args=(process.stdout, stdout_queue))
    stderr_thread = threading.Thread(target=read_output, args=(process.stderr, stderr_queue))
    stdout_thread.start()
    stderr_thread.start()
    
    # 实时输出并收集结果
    stdout_lines = []
    stderr_lines = []
    start_time = time.time()
    
    while stdout_thread.is_alive() or stderr_thread.is_alive() or process.poll() is None:
        try:
            # 从队列中读取 stdout
            while True:
                try:
                    line = stdout_queue.get_nowait()
                    print(line.strip())
                    stdout_lines.append(line)
                except queue.Empty:
                    break
            
            # 从队列中读取 stderr
            while True:
                try:
                    line = stderr_queue.get_nowait()
                    print(f"错误信息: {line.strip()}")
                    stderr_lines.append(line)
                except queue.Empty:
                    break
            
            # 检查超时
            if time.time() - start_time > timeout:
                process.terminate()
                print(f"错误：{description} 超时（超过 {timeout} 秒）")
                exit(1)
            
            time.sleep(0.1)  # 短暂休眠以减少 CPU 使用
        except Exception as e:
            print(f"读取输出时出错: {e}")
            break
    
    # 等待线程结束
    stdout_thread.join()
    stderr_thread.join()
    
    # 构造返回对象
    class CommandResult:
        def __init__(self, stdout, stderr, returncode):
            self.stdout = stdout
            self.stderr = "".join(stderr_lines)
            self.returncode = returncode
    
    result = CommandResult("".join(stdout_lines), "".join(stderr_lines), process.returncode)
    
    # 检查返回码
    if check and process.returncode != 0:
        print(f"错误：{description} 失败，返回码：{process.returncode}")
        exit(1)
    
    print(f"{description} 完成。")
    return result

def get_current_python_version():
    """获取当前 Python 版本"""
    return sys.version_info

def ensure_python_310():
    """检查并确保系统中可用 Python 3.10"""
    version = get_current_python_version()
    current_version = f"{version.major}.{version.minor}"
    print(f"当前运行脚本的 Python 版本: {current_version}")
    
    result = run_command(f"{PYTHON_CMD} --version", "检查 Python 3.10 是否可用", check=False)
    if result.returncode == 0:
        print(f"Python 3.10 已安装: {result.stdout.strip()}")
        return
    
    if not (version.major == 3 and 7 <= version.minor <= 10):
        print(f"当前版本 {current_version} 不兼容（需要 3.7-3.10），将安装 Python 3.10...")
        install_python()
    else:
        print(f"当前版本 {current_version} 兼容，但仍将确保 Python 3.10 可用...")
        install_python()

def install_python():
    print("下载并安装 Python 3.10...")
    installer = "python-installer.exe"
    try:
        response = requests.get(PYTHON_INSTALLER_URL, timeout=10)
        response.raise_for_status()
        with open(installer, "wb") as f:
            f.write(response.content)
    except requests.RequestException as e:
        print(f"下载 Python 安装程序失败：{e}")
        exit(1)
    run_command(f"{installer} /quiet InstallAllUsers=1 PrependPath=1", "安装 Python 3.10")
    if os.path.exists(installer):
        os.remove(installer)
    result = run_command(f"{PYTHON_CMD} --version", "验证 Python 3.10 安装", check=False)
    if result.returncode != 0:
        print("Python 3.10 安装失败，可能需要重启命令行或手动安装。")
        exit(1)
    print(f"Python 3.10 安装成功: {result.stdout.strip()}")

def download_and_extract_ffmpeg():
    """下载并解压 ffmpeg 和 ffprobe"""
    if not (os.path.exists("ffmpeg.exe") and os.path.exists("ffprobe.exe")):
        print("下载 ffmpeg 和 ffprobe...")
        ffmpeg_zip = "ffmpeg.zip"
        
        try:
            response = requests.get(FFMPEG_URL, timeout=10)
            response.raise_for_status()
            with open(ffmpeg_zip, "wb") as f:
                f.write(response.content)
        except requests.RequestException as e:
            print(f"下载 ffmpeg 失败：{e}")
            print("请检查网络连接或尝试手动下载 FFmpeg: https://github.com/BtbN/FFmpeg-Builds/releases/latest")
            exit(1)

        if not zipfile.is_zipfile(ffmpeg_zip):
            print("错误：下载的文件不是有效的 ZIP 文件。")
            print(f"文件大小：{os.path.getsize(ffmpeg_zip)} 字节")
            os.remove(ffmpeg_zip)
            exit(1)

        try:
            with zipfile.ZipFile(ffmpeg_zip, "r") as zip_ref:
                for file in zip_ref.namelist():
                    if "ffmpeg.exe" in file or "ffprobe.exe" in file:
                        zip_ref.extract(file, ".")
                        extracted_path = file
                        target_path = os.path.basename(file)
                        if os.path.exists(target_path):
                            os.remove(target_path)
                        os.rename(extracted_path, target_path)
            print("ffmpeg 和 ffprobe 下载并解压完成。")
        except zipfile.BadZipFile as e:
            print(f"解压失败：{e}")
            exit(1)
        finally:
            if os.path.exists(ffmpeg_zip):
                os.remove(ffmpeg_zip)
    else:
        print("ffmpeg 和 ffprobe 已存在，跳过下载。")

def clear_old_venv():
    """清除旧的虚拟环境"""
    if os.path.exists(VENV_DIR):
        print(f"检测到旧的虚拟环境 {VENV_DIR}，正在清除...")
        try:
            shutil.rmtree(VENV_DIR)
            print(f"旧虚拟环境 {VENV_DIR} 已清除。")
        except Exception as e:
            print(f"清除旧虚拟环境失败：{e}")
            print("请手动删除 RBVC 文件夹后重试。")
            exit(1)

def get_cuda_version():
    """在系统环境中检测 CUDA 版本"""
    print("尝试检测 CUDA 版本...")
    try:
        result = subprocess.run("nvcc --version", shell=True, text=True, capture_output=True)
        print(f"命令返回码: {result.returncode}")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        if result.returncode == 0:
            output = result.stdout.lower()  # 忽略大小写
            lines = output.splitlines()
            for i, line in enumerate(lines):
                print(f"{i} = '{line}'")  # 打印每行，便于调试
                if "release " in line:
                    # 提取版本号
                    version_part = line.split("release ")[1].split(",")[0].strip()
                    print(f"解析到的版本部分: {version_part}")
                    # 支持的 CUDA 版本
                    supported_versions = ["11.8", "12.4", "12.6", "12.8"]
                    if version_part in supported_versions:
                        return version_part
                    # 通用匹配
                    for ver in supported_versions:
                        if version_part.startswith(ver) or f"v{ver}" in line:
                            return ver
            print("未找到支持的 CUDA 版本（11.8, 12.4, 12.6, 12.8）")
        else:
            print(f"nvcc 命令执行失败，请检查环境变量 PATH")
    except Exception as e:
        print(f"检测 CUDA 时发生异常: {e}")
    return None

def install_pytorch(activate_cmd):
    cuda_version = get_cuda_version()
    if cuda_version is None:
        print("未检测到 CUDA 版本，请手动选择：")
        print("1. CUDA 11.8")
        print("2. CUDA 12.4")
        print("3. CUDA 12.6")
        print("4. CPU（无 CUDA）")
        choice = input("输入选择 (1-4): ").strip() or "1"
        cuda_version = {"1": "11.8", "2": "12.4", "3": "12.6", "4": None}.get(choice, "11.8")
    else:
        print(f"检测到 CUDA 版本: {cuda_version}")

    pytorch_commands = {
        "11.8": f"{activate_cmd} && pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118",
        "12.4": f"{activate_cmd} && pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124",
        "12.6": f"{activate_cmd} && pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126",
        None: f"{activate_cmd} && pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu"
    }
    
    cmd = pytorch_commands.get(cuda_version, pytorch_commands["11.8"])
    run_command(cmd, f"安装 PyTorch（CUDA {cuda_version or 'CPU'}）")

def main():
    # 0. 一开始检查并确保 Python 3.10 可用
    ensure_python_310()
    print(f"将使用 Python 命令: {PYTHON_CMD} 创建虚拟环境")

    # 1. 克隆仓库
    if not os.path.exists(PROJECT_DIR):
        run_command(f"git clone {GIT_URL} {PROJECT_DIR}", "克隆仓库")
    else:
        print("仓库已存在，跳过克隆。")

    # 2. 切换到项目目录
    os.chdir(PROJECT_DIR)

    # 3. 下载 ffmpeg 和 ffprobe
    download_and_extract_ffmpeg()

    # 4. 清除旧虚拟环境并使用 py -3.10 创建新虚拟环境
    clear_old_venv()
    run_command(f"{PYTHON_CMD} -m venv {VENV_DIR}", "创建虚拟环境 RBVC")
    result = run_command(f"{VENV_DIR}\\Scripts\\python.exe --version", "验证虚拟环境 Python 版本", check=False)
    print(f"虚拟环境 Python 版本: {result.stdout.strip()}")

    activate_cmd = f"call {VENV_DIR}\\Scripts\\activate"
    run_command(f"{activate_cmd} && python --version", "验证激活后的 Python 版本")
    
    install_pytorch(activate_cmd)
    
    print("\n请选择您的 GPU 类型：")
    print("1. Nvidia (默认)")
    print("2. AMD")
    gpu_choice = input("输入选择 (1 或 2): ").strip() or "1"
    
    if gpu_choice == "1":
        requirements_file = "requirements.txt"
    elif gpu_choice == "2":
        requirements_file = "requirements-dml.txt"
    else:
        print("无效选择，默认使用 Nvidia 配置。")
        requirements_file = "requirements.txt"
    
    run_command(f"{activate_cmd} && pip install -r {requirements_file}", "安装其他依赖")
    run_command(f"{activate_cmd} && python tools\\downloadmodels.py", "下载预训练模型")
    
    print("\n部署完成，即将启动 Web UI...")
    run_command(f"{activate_cmd} && python infer-web.py", "启动 Web UI")

if __name__ == "__main__":
    print("开始一键部署 Retrieval-based-Voice-Conversion-WebUI...")
    print("请确保已安装 Git 并具有网络连接。\n")
    main()