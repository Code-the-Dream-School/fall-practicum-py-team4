import plotly.graph_objects as go

METRICS = {
    'AQI': ('aqi', 'AQI (1–5)', 'aqi_rolling_7d'),
    'PM2.5': ('pm2_5', 'µg/m³', 'pm2_5_rolling_7d'),
    'CO': ('co', 'µg/m³', None),
    'NO₂': ('no2', 'µg/m³', None),
}


def create_time_series(df, metric, granularity, show_rolling):
    column, unit, rolling = METRICS[metric]
    daily = granularity == 'Daily'
    date_format = '%b %d, %Y' if daily else '%b %d, %Y %H:%M UTC'
    hover = (
        '<b>%{x|' + date_format + '}</b><br>'
        + ('Daily averages<br>' if daily else 'Hourly measurements<br>')
        + 'AQI: %{customdata[0]:.2f}<br>'
        + 'PM2.5: %{customdata[1]:.2f} µg/m³<br>'
        + 'CO: %{customdata[2]:.2f} µg/m³<br>'
        + 'NO₂: %{customdata[3]:.2f} µg/m³'
    )
    if show_rolling and rolling:
        hover += '<br>7-day rolling average: %{customdata[4]:.2f}'
    hover += '<extra></extra>'
    custom_columns = ['aqi', 'pm2_5', 'co', 'no2']
    if show_rolling and rolling:
        custom_columns.append(rolling)
    custom = df[custom_columns].to_numpy()
    fig = go.Figure()
    label = f'{metric} daily mean' if granularity == 'Daily' else metric
    fig.add_trace(go.Scatter(
        x=df['date_time'], y=df[column], name=label,
        mode='lines+markers' if granularity == 'Daily' else 'lines',
        line=dict(color='#0d9488', width=2), connectgaps=False,
        customdata=custom, hovertemplate=hover,
    ))
    if show_rolling and rolling:
        fig.add_trace(go.Scatter(
            x=df['date_time'], y=df[rolling], name='7-day rolling average',
            mode='lines', line=dict(color='#d97706', dash='dash'),
            connectgaps=False, customdata=custom, hovertemplate=hover,
        ))
    fig.update_layout(
        height=420, margin=dict(l=15, r=15, t=20, b=15),
        xaxis_title='Date' if daily else 'Date and time (UTC)', yaxis_title=unit,
        hovermode='closest', legend=dict(orientation='h', y=1.12),
    )
    if daily:
        fig.update_xaxes(tickformat='%b %d, %Y', dtick=86400000 if len(df) <= 14 else 604800000)
    if metric == 'AQI':
        fig.update_yaxes(range=[0.8, 5.2], dtick=1)
    return fig
