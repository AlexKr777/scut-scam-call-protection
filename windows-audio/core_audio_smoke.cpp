#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
int main() { IMMDeviceEnumerator* e=nullptr; HRESULT h=CoInitializeEx(nullptr,COINIT_MULTITHREADED); if(SUCCEEDED(h)) { h=CoCreateInstance(__uuidof(MMDeviceEnumerator),nullptr,CLSCTX_ALL,__uuidof(IMMDeviceEnumerator),(void**)&e); if(e)e->Release(); CoUninitialize(); } return FAILED(h); }
