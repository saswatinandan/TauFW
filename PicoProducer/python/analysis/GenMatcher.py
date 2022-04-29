#! /usr/bin/env python
# Author: Izaak Neutelings (April 2022)
# Description: Study genmatch algorithms in nanoAOD
# HTT gen-matching:
#   https://twiki.cern.ch/twiki/bin/viewauth/CMS/HiggsToTauTauWorking2016#MC_Matching
#   https://indico.cern.ch/event/439324/#19-studies-on-background-categ
# NanoAOD genPartFlav:
#   https://github.com/cms-sw/cmssw/blob/master/PhysicsTools/NanoAOD/plugins/CandMCMatchTableProducer.cc
# Previous bug in nanoAOD genPartFlav:
#   https://indico.cern.ch/event/801245/#3-data-mc-agreement-in-run-2-t
#   https://github.com/cms-sw/cmssw/issues/26163
# Instructions:
#   pico.py channel genmatch GenMatcher
#   pico.py run -c genmatch -s DYJetsToLL_M-50 -y UL2018 -m 1000
#   pico.py submit -c genmatch -s DYJetsToLL_M-50 -y UL2018
#   pico.py status -c genmatch -s DYJetsToLL_M-50 -y UL2018
#   pico.py hadd -c genmatch -s DYJetsToLL_M-50 -y UL2018
#   python/analysis/GenMatcher.py DYJetsToLL_M-50_genmatch.root
#   tree->Draw("genmatch_HTT:genmatch >> h(7,0,7,7,0,7)","","COLZ TEXT")
#   tree->Draw("genmatch_HTT:genmatch >> h(7,0,7,7,0,7)","idDeepTau2017v2p1VSe>=2 && idDeepTau2017v2p1VSmu>=2 && idDeepTau2017v2p1VSjet>=8 && pt>40","COLZ TEXT")
import ROOT; ROOT.PyConfig.IgnoreCommandLineOptions = True
import re
from ROOT import TH2D, gStyle, kRed
from TreeProducer import TreeProducer
from PhysicsTools.NanoAODTools.postprocessing.framework.eventloop import Module
from PhysicsTools.NanoAODTools.postprocessing.framework.datamodel import Collection, Event
from TauFW.PicoProducer.analysis.utils import hasbit


class GenMatcher(Module):
  """Simple module to check genmatching algorithms."""
  
  def __init__(self,fname,**kwargs):
    self.out = TreeProducerGenMatcher(fname,self)
    
  def endJob(self):
    """Wrap up after running on all events and files"""
    self.out.endJob()
    
  def analyze(self, event):
    """Process event, return True (pass, go to next module) or False (fail, go to next event)."""
    self.out.cutflow.fill('none')
    
    # TAU
    # https://cms-nanoaod-integration.web.cern.ch/integration/master-102X/mc102X_doc.html#Tau
    taus = [ ] # selected tau candidates
    for tau in Collection(event,'Tau'):
      if tau.pt<20: continue
      if abs(tau.eta)>2.3: continue
      #if abs(tau.dz)>0.2: continue
      #if tau.decayMode not in [0,1,10,11]: continue
      #if abs(tau.charge)!=1: continue
      if tau.idDeepTau2017v2p1VSe<1: continue # VVVLoose
      if tau.idDeepTau2017v2p1VSmu<1: continue # VLoose
      if tau.idDeepTau2017v2p1VSjet<1: continue # VVVLoose
      taus.append(tau)
    if len(taus)==0:
      return False
    self.out.cutflow.fill('tau')
    if len(taus)>=2:
      self.out.cutflow.fill('taus')
    #tau = max(taus,key=lambda t: t.pt) # select tau with highest pT
    
    # STORE EACH TAU
    for tau in taus:
      
      # HTT GENMATCH ALGORITHMS
      genmatch_HTT = genmatch(tau,event,cutpt=True)
      genmatch_HTT_nopt = genmatch(tau,event,cutpt=False)
      
      # FILL HISTOGRAMS
      self.out.h_gm_HTT_vs_nano.Fill(tau.genPartFlav,genmatch_HTT)
      self.out.h_gm_HTT_nopt_vs_nano.Fill(tau.genPartFlav,genmatch_HTT_nopt)
      self.out.h_gm_HTT_vs_HTT_nopt.Fill(genmatch_HTT_nopt,genmatch_HTT)
      
      # FILL TREE BRANCHES
      self.out.pt[0]                     = tau.pt
      self.out.eta[0]                    = tau.eta
      self.out.phi[0]                    = tau.phi
      self.out.m[0]                      = tau.mass
      self.out.q[0]                      = tau.charge
      self.out.dm[0]                     = tau.decayMode
      self.out.genmatch[0]               = tau.genPartFlav # default nanoAOD genmatch
      self.out.genmatch_HTT[0]           = genmatch_HTT
      self.out.genmatch_HTT_nopt[0]      = genmatch_HTT_nopt
      self.out.idDecayMode[0]            = tau.idDecayMode
      self.out.idDecayModeNewDMs[0]      = tau.idDecayModeNewDMs
      self.out.idDeepTau2017v2p1VSe[0]   = tau.idDeepTau2017v2p1VSe
      self.out.idDeepTau2017v2p1VSmu[0]  = tau.idDeepTau2017v2p1VSmu
      self.out.idDeepTau2017v2p1VSjet[0] = tau.idDeepTau2017v2p1VSjet
      self.out.ntaus[0]                  = len(taus)
      ###if genmatch_HTT==5:
      ###  self.out.genpt[0]                = gmobj_HTT.pt
      ###  self.out.genid[0]                = gmobj_HTT.status
      ###elif 0<genmatch_HTT<5:
      ###  self.out.genpt[0]                = gmobj_HTT.pt
      ###  self.out.genid[0]                = gmobj_HTT.pdgId
      ###else:
      ###  self.out.genpt[0]                = -1
      ###  self.out.genid[0]                = -99
      self.out.fill()
      
    return True
    

def genmatch(tau,event,cutpt=True):
  """HTT-prescribed genmatching for reconstructed taus to generator electrons, muons and taus."""
  # https://twiki.cern.ch/twiki/bin/viewauth/CMS/HiggsToTauTauWorking2016#MC_Matching
  genmatch = 0 # gen-match code, default: 0 (or 6) = no match (assumed from jet)
  dRmin    = 0.2
  ###gmobj    = None # matched object
  
  # FAKE lepton -> tau
  for particle in Collection(event,'GenPart'):
    pid = abs(particle.pdgId)
    #if particle.status!=1 and pid!=13: continue
    if cutpt and particle.pt<8: continue
    if pid not in [11,13]: continue
    dR = tau.DeltaR(particle)
    if dR<dRmin:
      # https://cms-nanoaod-integration.web.cern.ch/integration/master-102X/mc102X_doc.html#GenPart
      if hasbit(particle.statusFlags,0): # isPrompt
        if   pid==11: genmatch = 1; dRmin = dR; ###gmobj = particle
        elif pid==13: genmatch = 2; dRmin = dR; ###gmobj = particle
      elif hasbit(particle.statusFlags,5): # isDirectPromptTauDecayProduct
        if   pid==11: genmatch = 3; dRmin = dR; ###gmobj = particle
        elif pid==13: genmatch = 4; dRmin = dR; ###gmobj = particle
  
  # REAL (visible system of the) tau leptons
  # Gen-tau jet, rebuilt from sum of 4-momenta of visible gen tau decay products, excluding electrons and muons
  for gentau in Collection(event,'GenVisTau'):
    if cutpt and gentau.pt<15: continue
    dR = tau.DeltaR(gentau)
    if dR<dRmin:
      dRmin = dR
      genmatch = 5
      ###gmobj = gentau
  
  return genmatch ###, gmobj
  


class TreeProducerGenMatcher(TreeProducer):
  
  def __init__(self, filename, module, **kwargs):
    """Class to create and prepare a custom output file & tree."""
    super(TreeProducerGenMatcher,self).__init__(filename,module,**kwargs)
    
    # ONLY JOB (no hadd)
    self.localjob = bool(re.search(r"(-\d+|[^\d])$",filename.replace(".root","")))
    self.onlyjob = self.localjob or bool(re.search(r"_0$",filename.replace(".root","")))
    
    # CUTFLOW
    self.cutflow.addcut('none', "no cut" )
    self.cutflow.addcut('tau',  "tau"    )
    self.cutflow.addcut('taus', "#geq2 taus" )
    
    # HISTOGRAMS
    self.h_gm_HTT_vs_nano      = TH2D('h_gm_HTT_vs_nano',     ";Tau gen-match nanoAOD;Tau gen-match HTT;Events",7,0,7,7,0,7)
    self.h_gm_HTT_nopt_vs_nano = TH2D('h_gm_HTT_nopt_vs_nano',";Tau gen-match nanoAOD;Tau gen-match HTT (no pT cut);Events",7,0,7,7,0,7)
    self.h_gm_HTT_vs_HTT_nopt  = TH2D('h_gm_HTT_vs_HTT_nopt', ";Tau gen-match HTT (no pT cut);Tau gen-match HTT;Events",7,0,7,7,0,7)
    
    # TREE BRANCHES
    self.addBranch('pt',                     'f')
    self.addBranch('eta',                    'f')
    self.addBranch('phi',                    'f')
    self.addBranch('m',                      'f')
    self.addBranch('q',                      'f', title="Charge")
    self.addBranch('dm',                     'i')
    self.addBranch('genmatch',               'i', title="gen-match, default nanoAOD (Tau_genPartFlav)")
    self.addBranch('genmatch_HTT',           'i', title="gen-match, HTT-prescription, incl. pT cuts")
    self.addBranch('genmatch_HTT_nopt',      'i', title="gen-match, HTT-prescription, no pT cuts")
    self.addBranch('idDecayMode',            '?', title="oldDecayModeFinding")
    self.addBranch('idDecayModeNewDMs',      '?', title="newDecayModeFinding")
    self.addBranch('idDeepTau2017v2p1VSe',   'i')
    self.addBranch('idDeepTau2017v2p1VSmu',  'i')
    self.addBranch('idDeepTau2017v2p1VSjet', 'i')
    self.addBranch('ntaus',                  'i', title="number of selected tau candidates in this event")
    ###self.addBranch('genpt',                  'f', title="pt of gen-matched object")
    ###self.addBranch('genid',                  'f', title="id of gen-matched object")
    
  def endJob(self):
    """Write and close files after the job ends."""
    
    # PREPARE HISTOGRAMS
    self.outfile.cd()
    self.hnorms = [ ] # store new histograms before writing
    for hist in [self.h_gm_HTT_vs_nano,self.h_gm_HTT_nopt_vs_nano,self.h_gm_HTT_vs_HTT_nopt]:
      nxbins = hist.GetXaxis().GetNbins()
      nybins = hist.GetYaxis().GetNbins()
      for ix in range(1,nxbins+1): # loop over columns
        hist.GetXaxis().SetBinLabel(ix,str(ix-1)) # set alphanumerical bin label
        if hist.GetBinContent(ix,0)!=0: # check underflow
          print ">>> WARNING!!! Underflow in (ix,0)=(%s,0) of %r"%(ix,hist.GetName())
        if hist.GetBinContent(ix,nybins+1)!=0: # check overflow
          print ">>> WARNING!!! Overflow in (ix,nybins+1)=(%s,%s) of %r"%(ix,nybins+1,hist.GetName())
      for iy in range(1,nybins+1): # loop over rows
        hist.GetYaxis().SetBinLabel(iy,str(iy-1)) # set alphanumerical bin label
        if hist.GetBinContent(0,iy)!=0: # check underflow
          print ">>> WARNING!!! Underflow in (0,iy)=(0,%s) of %r"%(iy,hist.GetName())
        if hist.GetBinContent(nxbins+1,iy)!=0: # check overflow
          print ">>> WARNING!!! Overflow in (nxbins+1,iy)=(%s,%s) of %r"%(nxbins+1,iy,hist.GetName())
      hist.SetMarkerColor(kRed)
      hist.SetMarkerSize(1.5)
      hist.GetXaxis().SetNdivisions(10)
      hist.GetYaxis().SetNdivisions(10)
      hist.GetXaxis().SetLabelSize(0.058)
      hist.GetYaxis().SetLabelSize(0.058)
      hist.GetXaxis().SetLabelOffset(0.003)
      hist.GetYaxis().SetLabelOffset(0.002)
      hist.GetXaxis().SetTitleSize(0.048)
      hist.GetYaxis().SetTitleSize(0.048)
      hist.GetZaxis().SetTitleSize(0.048)
      hist.GetZaxis().SetTitle("Taus")
      hist.SetOption('COLZ TEXT22') # preset default draw option
      if self.localjob:
        hnorm = normalize(hnorm,hist.GetName()+"_norm") # normalize columns
        hnorm.SetDirectory(self.outfile) # ensure write to ouput file
        self.hnorms.append(hnorm) # store new histograms before writing
    
    # WRITE
    if self.onlyjob: # only store for first job output
      #gStyle.SetOptTitle(False) # don't make title on top of histogram
      gStyle.SetOptStat(False)  # don't make stat. box
      gStyle.SetPaintTextFormat('d') # integer (events)
      gStyle.Write("style_evts")
      gStyle.SetPaintTextFormat('.1f') # percentage (fraction)
      gStyle.Write("style_frac")
    super(TreeProducerGenMatcher,self).endJob()
    

def normalize(hist,hname=None,row=False):
  """Normalize rows (row=True) or columns (row=False) of 2D histogram."""
  if hname: # create new histogram
    hist = hist.Clone(hname)
  nxbins = hist.GetXaxis().GetNbins()
  nybins = hist.GetYaxis().GetNbins()
  hist.SetMarkerSize(2) # draw with "COLZ TEXT"
  hist.SetTitle("Normalized columns")
  hist.SetOption('COLZ TEXT') # preset default draw option
  if row:
    hist.GetZaxis().SetTitle("Row fraction [%]")
    for iy in range(1,nybins+1): # loop over rows
      ntot = sum(hist.GetBinContent(ix,iy) for ix in range(1,nxbins+1)) # sum row at iy
      if ntot<=0: continue
      for ix in range(1,nxbins+1): # normalize rows
        frac = 100.0*hist.GetBinContent(ix,iy)/ntot # fraction of column
        hist.SetBinContent(ix,iy,frac) # overwrite number of events with fraction
  else:
    hist.GetZaxis().SetTitle("Column fraction [%]")
    for ix in range(1,nxbins+1): # loop over columns
      ntot = sum(hist.GetBinContent(ix,iy) for iy in range(1,nybins+1)) # sum column at ix
      if ntot<=0: continue
      for iy in range(1,nybins+1): # normalize rows
        frac = 100.0*hist.GetBinContent(ix,iy)/ntot # fraction of column
        hist.SetBinContent(ix,iy,frac) # overwrite number of events with fraction
  return hist
  

# SCRIPT
if __name__ == '__main__':
  from ROOT import gROOT, TFile, TCanvas
  from argparse import ArgumentParser
  gROOT.SetBatch(True)      # don't open GUI windows
  gStyle.SetOptTitle(False) # don't make title on top of histogram
  gStyle.SetOptStat(False)  # don't make stat. box
  gStyle.SetPaintTextFormat('.2f') # integer (events)
  description = """Make histograms from output file."""
  parser = ArgumentParser(prog="GenMatcher",description=description,epilog="Good luck!")
  parser.add_argument('file', help="final (hadd'ed) ROOT file")
  parser.add_argument('-t',"--tag", default="", help="extra tag for output file")
  args = parser.parse_args()
  file = TFile.Open(args.file)
  hnames = ['h_gm_HTT_vs_nano','h_gm_HTT_nopt_vs_nano','h_gm_HTT_vs_HTT_nopt']
  for hname in hnames:
    hist = file.Get(hname)
    hist.GetXaxis().SetLabelSize(0.075)
    hist.GetYaxis().SetLabelSize(0.075)
    hist.GetZaxis().SetLabelSize(0.046)
    hist.GetXaxis().SetTitleSize(0.054)
    hist.GetYaxis().SetTitleSize(0.054)
    hist.GetZaxis().SetTitleSize(0.054)
    hist.GetXaxis().SetTitleOffset(0.95)
    hist.GetYaxis().SetTitleOffset(0.80)
    hist.GetZaxis().SetTitleOffset(0.95)
    hist.GetXaxis().SetLabelOffset(0.005)
    hist.GetYaxis().SetLabelOffset(0.004)
    for direction in ['row','col']:
      pname = "%s_%s%s"%(hname.replace("h_gm","genmatch"),direction,args.tag)
      hnorm = normalize(hist,pname,row=(direction=='row'))
      canvas = TCanvas('canvas','canvas',100,100,800,600)
      canvas.SetMargin(0.09,0.15,0.11,0.02) # LRBT
      hnorm.SetMaximum(100)
      hnorm.Draw('COLZ TEXT')
      canvas.SaveAs(pname+".png")
      canvas.SaveAs(pname+".pdf")
      canvas.Close()
  file.Close()
  print ">>> Done."
  
