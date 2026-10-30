import numpy as np, soundfile as sf
from scipy.signal import butter, sosfilt
SR=48000; rng=np.random.default_rng(7)
def bp(x,lo,hi,o=4): return sosfilt(butter(o,[lo,hi],'bandpass',fs=SR,output='sos'),x)
def lp(x,f,o=4): return sosfilt(butter(o,f,'lowpass',fs=SR,output='sos'),x)
def tv_bp(x,f0,f1,q=1.2,n=64):
    # time-varying bandpass via overlapped blocks
    L=len(x); out=np.zeros(L); hop=L//n; win=np.hanning(2*hop)
    for i in range(n):
        a=max(0,i*hop-hop//2); b=min(L,a+2*hop); f=f0*(f1/f0)**(i/(n-1))
        seg=bp(x[max(0,a-2048):b],max(30,f/q),min(SR/2-100,f*q),2)[-(b-a):]
        out[a:b]+=seg*win[:b-a]
    return out
def env_ad(n,att,rel_pow=1.0):
    t=np.linspace(0,1,n); a=int(att*n); e=np.ones(n)
    e[:a]=np.linspace(0,1,a)**2; e[a:]=(1-np.linspace(0,1,n-a))**rel_pow; return e
def save(name,x): x=x/np.abs(x).max()*0.7; sf.write(f"synth/{name}.wav",x.astype(np.float32),SR); print(name,len(x)/SR)
# riser noise 2s: noise bandpass sweeping up + growing level
n=2*SR; t=np.arange(n)/SR
x=tv_bp(rng.standard_normal(n),300,9000,1.5)*np.linspace(0.05,1,n)**2.2; x[-int(.01*SR):]*=np.linspace(1,0,int(.01*SR)); save("riser_noise2s",x)
# riser tonal 4s: saw-ish chord gliding up + noise
n=4*SR; t=np.arange(n)/SR; f=110*2**(t/4*2)  # two octaves
ph=2*np.pi*np.cumsum(f)/SR; tone=sum(np.sin(k*ph)/k for k in range(1,8))+0.5*sum(np.sin(k*ph*1.5)/k for k in range(1,5))
x=tone*0.6+tv_bp(rng.standard_normal(n),500,10000,1.5)*0.8; x*=np.linspace(0.02,1,n)**2.5; x[-int(.01*SR):]*=np.linspace(1,0,int(.01*SR)); save("riser_tonal4s",x)
# impact sub boom: 808-ish pitch drop + click + noise tail
n=int(1.6*SR); t=np.arange(n)/SR; f=45+120*np.exp(-t*18); ph=2*np.pi*np.cumsum(f)/SR
x=np.tanh(1.8*np.sin(ph)*np.exp(-t*2.8)); x+=lp(rng.standard_normal(n),3000)*np.exp(-t*40)*0.6; save("impact_subboom",x)
# impact cinematic hit: boom + mid thud + reverb-ish noise tail
n=int(2.2*SR); t=np.arange(n)/SR; f=38+90*np.exp(-t*10); ph=2*np.pi*np.cumsum(f)/SR
x=np.sin(ph)*np.exp(-t*1.8)+lp(rng.standard_normal(n),1800)*np.exp(-t*6)*0.5+bp(rng.standard_normal(n),200,6000)*np.exp(-t*25)*0.7; save("impact_cinehit",np.tanh(1.5*x))
# whoosh long 1.2s: noise sweep up then down, swelling
n=int(1.2*SR); t=np.linspace(0,1,n); nz=rng.standard_normal(n)
a=tv_bp(nz[:n//2+1],250,2500,1.3,32); b=tv_bp(nz[n//2:],2500,350,1.3,32); x=np.concatenate([a,b])[:n]
x*=np.sin(np.pi*t)**2.5; save("whoosh_long_synth",x)
# paper tear: crackly noise bursts, bandlimited, ~0.7s, accelerating
n=int(0.75*SR); t=np.linspace(0,1,n); x=np.zeros(n); pos=0
while pos<n-400:
    L=int(rng.uniform(40,350)); g=rng.uniform(0.3,1.0)*(0.6+0.4*np.sin(np.pi*pos/n))
    x[pos:pos+L]+=rng.standard_normal(L)*g*np.hanning(L); pos+=int(rng.uniform(60,420)*(1.2-0.6*pos/n))
x=bp(x,1200,11000)+0.25*bp(rng.standard_normal(n),3000,9000)*np.sin(np.pi*t)
x*=np.clip(t*12,0,1)*(1-t)**0.6; save("paper_tear_synth",x)
# sticker boing: sine with vibrato glide
n=int(0.55*SR); t=np.arange(n)/SR; f=320+260*np.exp(-t*7)*np.cos(2*np.pi*14*t); ph=2*np.pi*np.cumsum(f)/SR
x=(np.sin(ph)+0.3*np.sin(2*ph))*np.exp(-t*7)*np.clip(t*400,0,1); save("sticker_boing_synth",x)
# text pop synth: short pitched blip (bubble)
n=int(0.12*SR); t=np.arange(n)/SR; f=500+900*(t/t[-1])**0.5; ph=2*np.pi*np.cumsum(f)/SR
x=np.sin(ph)*np.exp(-t*45)*np.clip(t*2000,0,1); save("text_pop_synth",x)
