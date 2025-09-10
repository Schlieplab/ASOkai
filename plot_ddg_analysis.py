import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib.patches import FancyBboxPatch

# Data
ddg_thresholds = [0.1, 1, 3, 5, 10]  # Using 0.1 instead of 0 for log scale
off_targets = [7936655, 8207631, 8294815, 8300175, 8300354]
# Convert time to minutes
time_minutes = [6, 11, 26, 54, 142]  # 2 hours 22 minutes = 142 minutes

# Calculate percentages for off-targets
max_off_targets = max(off_targets)
off_targets_percentages = [x/max_off_targets*100 for x in off_targets]

# Set style and color palette with LaTeX-style fonts
plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'DejaVu Serif', 'serif'],
    'text.usetex': False,
    'mathtext.fontset': 'dejavuserif',
    'axes.linewidth': 0.8,
    'grid.linewidth': 0.5,
    'lines.linewidth': 1.5,
    'patch.linewidth': 0.5,
    'xtick.major.width': 0.8,
    'ytick.major.width': 0.8,
    'xtick.minor.width': 0.4,
    'ytick.minor.width': 0.4
})

# Minimalistic color palette
colors = ['#2E86AB', '#A23B72']

# Create figure with two subplots
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
fig.patch.set_facecolor('white')

# Add main title for the entire figure
fig.suptitle('Impact of ∆∆G Tolerance on Off-target Analysis (Gene=KRAS, k=16, layout=4,8,4)', fontsize=16, color='black', y=0.98)

# Plot off-targets with minimalistic styling
ax1.semilogx(ddg_thresholds, off_targets, 
             color='#2E86AB', linewidth=2, markersize=6,
             marker='o', markerfacecolor='#2E86AB', markeredgecolor='white',
             markeredgewidth=1, alpha=0.9, zorder=3)

ax1.set_xlabel('∆∆G Tolerance', fontsize=12, color='black')
ax1.set_ylabel('Number of Off-targets', fontsize=12, color='black')
ax1.set_title('Off-targets vs ∆∆G Tolerance', fontsize=14, color='black', pad=15)

# Minimalistic grid
ax1.grid(True, linestyle='-', alpha=0.2, color='gray', linewidth=0.5, zorder=0)
ax1.set_facecolor('white')

# Format y-axis with commas for better readability
ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))

# Add minimalistic percentage labels
for i, (x, y, pct) in enumerate(zip(ddg_thresholds, off_targets, off_targets_percentages)):
    ax1.annotate(f'{pct:.1f}%', 
                xy=(x, y), 
                xytext=(0, 10),  # 10 points vertical offset
                textcoords='offset points',
                ha='center', va='bottom',
                fontsize=12, color='black', zorder=4)

# Set x-axis ticks and labels
ax1.set_xticks(ddg_thresholds)
ax1.set_xticklabels(['0', '1', '3', '5', '∞'], fontsize=11)
ax1.tick_params(axis='both', which='major', labelsize=10, colors='black')

# Clean spines
for spine in ax1.spines.values():
    spine.set_edgecolor('black')
    spine.set_linewidth(0.8)

# Plot computation time with minimalistic styling
ax2.semilogx(ddg_thresholds, time_minutes, 
             color='#A23B72', linewidth=2, markersize=6,
             marker='s', markerfacecolor='#A23B72', markeredgecolor='white',
             markeredgewidth=1, alpha=0.9, zorder=3)

ax2.set_xlabel('∆∆G Tolerance', fontsize=12, color='black')
ax2.set_ylabel('Computation Time (minutes)', fontsize=12, color='black')
ax2.set_title('Computation Time vs ∆∆G Tolerance', fontsize=14, color='black', pad=15)

# Minimalistic grid
ax2.grid(True, linestyle='-', alpha=0.2, color='gray', linewidth=0.5, zorder=0)
ax2.set_facecolor('white')

# Set x-axis ticks and labels
ax2.set_xticks(ddg_thresholds)
ax2.set_xticklabels(['0', '1', '3', '5', '∞'], fontsize=11)
ax2.tick_params(axis='both', which='major', labelsize=10, colors='black')

# Add minimalistic value labels
for i, (x, y) in enumerate(zip(ddg_thresholds, time_minutes)):
    ax2.annotate(f'{y} min', 
                xy=(x, y), 
                xytext=(0, 10),  # 10 points vertical offset
                textcoords='offset points',
                ha='center', va='bottom',
                fontsize=12, color='black', zorder=4)

# Clean spines
for spine in ax2.spines.values():
    spine.set_edgecolor('black')
    spine.set_linewidth(0.8)

# Adjust layout and save
plt.tight_layout(pad=1.0, rect=[0, 0, 1, 0.96])  # Leave space for suptitle
plt.savefig('ddg_analysis.png', dpi=300, bbox_inches='tight', 
            facecolor='white', edgecolor='none')
plt.close()