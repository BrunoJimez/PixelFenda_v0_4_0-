from pixelfenda.stems import demucs_available, demucs_python
print('Python Demucs:', demucs_python())
print('Demucs:', 'OK' if demucs_available() else 'nao detectado')
try:
    import subprocess
    p=demucs_python()
    r=subprocess.run([p,'-c','import torch; print(torch.__version__); print("CUDA:",torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU")'],capture_output=True,text=True,timeout=15)
    print(r.stdout.strip() or r.stderr.strip())
except Exception as exc:
    print('PyTorch/CUDA:',exc)
