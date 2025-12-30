# Raw data/images
DSCOVR data: https://www.ngdc.noaa.gov/dscovr/portal/index.html#/download/1763510400000;1763855999999/mg1
GOES-18 data: https://data.ngdc.noaa.gov/platforms/solar-space-observing-satellites/goes/goes18/l1b/mag-l1b-flat/
keograms: https://optics.gi.alaska.edu/amisr_archive/Processed_data/aurorax/stream2/
allsky videos: https://optics.gi.alaska.edu/realtime/data/MPEG/PKR_DASC_512/

# Directory Layout (defaults)
~/Documents/keogram_project/<br/>
&emsp;interactive_stacks/               # contains necessary files to create keogram_YYYYMM.html within YYYYMM folders<br/>
  &emsp;YYYYMM/<br/>
    &emsp;stacked_keograms_YYYYMM.png   # output from stack_keograms.py (year/stacked_keograms_YYYYMM.png)<br/>
    &emsp;keogram_YYYYMM.html           # currently created by duplicating similar .html and adjusting for appropriate YYYYMM<br/>
    &emsp;keogram_meta_YYYYMM.json      # output from build_keogram_meta.py<br/>
    &emsp;video_meta_YYYYMM.json        # output from build_video_meta.py<br/>
&emsp;overlaid_full/                    # outputs from create_keogram_plots.py (full)<br/>
&emsp;overlaid_partial/                 # outputs from create_keogram_plots.py (partial)<br/>
&emsp;stacked_by_month/                 # outputs from stack_keograms.py (year/stacked_keograms_YYYYMM.png)<br/>
&emsp;scripts/                          # the Python scripts (in Git)<br/>
  &emsp;requirements.txt                # must install before attempting to run any scripts<br/>
  &emsp;create_keogram_plots.py         # overlays keograms with GOES and DSCOVR data, either range of dates or range of hours<br/>
  &emsp;stack_keograms.py               # stacks all keograms from requested month verticaly, no overlaid data<br/>
  &emsp;build_keogram_meta.py           # writes json with info on each keogram within requested month<br/>
  &emsp;build_video_meta.py             # writes json with info on each allsky video within requested month<br/>
  &emsp;build_stack_html.py             # creates insteractive stack html<br/>
  &emsp;build_interactive_stack.py      # runs 4 above scripts (build_....py) for requsted month all at once<br/>


# Instructions for creating an interactive stack
1. Clone git
  ```
  git clone https://github.com/anniepflaum/keogram-plots
  ```
2. Activate virtual environment
    python3 -m venv .venv
    source .venv/bin/activate
3. Upgrade pip, install requirements
    python -m pip install --upgrade pip
    pip install -r requirements.txt