import matplotlib.pyplot as plt
import numpy as np

# Data
ddg_thresholds = [0.1, 1, 3, 5, 100]  # Using 0.1 instead of 0 for log scale
off_targets = [7936655, 8207631, 8294815, 8300175, 8300354]
# Convert time to minutes
time_minutes = [6, 11, 26, 54, 142]  # 2 hours 22 minutes = 142 minutes

# Calculate percentages for off-targets
max_off_targets = max(off_targets)
off_targets_percentages = [x/max_off_targets*100 for x in off_targets]

# Create figure with two subplots
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))

# Plot off-targets
ax1.semilogx(ddg_thresholds, off_targets, 'bo-', linewidth=2, markersize=8)
ax1.set_xlabel('DDG Threshold', fontsize=12)
ax1.set_ylabel('Number of Off-targets', fontsize=12)
ax1.set_title('Off-targets vs DDG Threshold', fontsize=14, pad=10)
ax1.grid(True, linestyle='--', alpha=0.7)

# Format y-axis with commas for better readability
ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))

# Add percentage labels above each point
for i, (x, y, pct) in enumerate(zip(ddg_thresholds, off_targets, off_targets_percentages)):
    ax1.annotate(f'{pct:.1f}%', 
                xy=(x, y), 
                xytext=(0, 10),  # 10 points vertical offset
                textcoords='offset points',
                ha='center',
                va='bottom')

# Set x-axis ticks and labels
ax1.set_xticks(ddg_thresholds)
ax1.set_xticklabels(['0', '1', '3', '5', '100'])  # Show 0 instead of 0.1

# Plot computation time
ax2.semilogx(ddg_thresholds, time_minutes, 'ro-', linewidth=2, markersize=8)
ax2.set_xlabel('DDG Threshold', fontsize=12)
ax2.set_ylabel('Computation Time (minutes)', fontsize=12)
ax2.set_title('Computation Time vs DDG Threshold', fontsize=14, pad=10)
ax2.grid(True, linestyle='--', alpha=0.7)

# Set x-axis ticks and labels
ax2.set_xticks(ddg_thresholds)
ax2.set_xticklabels(['0', '1', '3', '5', '100'])  # Show 0 instead of 0.1

# Adjust layout and save
plt.tight_layout()
plt.savefig('ddg_analysis.png', dpi=300, bbox_inches='tight')
plt.close() 