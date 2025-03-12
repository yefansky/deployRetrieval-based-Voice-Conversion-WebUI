@echo off
cd Retrieval-based-Voice-Conversion-WebUI
call RBVC\Scripts\activate
python infer-web.py
pause