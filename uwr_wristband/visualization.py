"""Build a plotly Figure from fullcontrol steps for Streamlit display."""

from __future__ import annotations

from typing import List

import plotly.graph_objects as go

import fullcontrol as fc


def generate_preview_figure(
    steps: List,
    EW: float = 0.5,
    EH: float = 0.2,
) -> go.Figure:
    """Return an interactive plotly ``Figure`` showing the extrusion paths.

    Uses ``raw_data=True`` so fullcontrol returns a ``PlotData`` object
    instead of calling ``fig.show()``, letting us build the figure ourselves
    for embedding in Streamlit.
    """
    plot_controls = fc.PlotControls(
        style="line",
        raw_data=True,
        initialization_data={
            "extrusion_width": EW,
            "extrusion_height": EH,
        },
    )
    plot_data = fc.transform(steps, "plot", plot_controls, show_tips=False)

    fig = go.Figure()
    for path in plot_data.paths:
        if not path.extruder or not path.extruder.on:
            continue  # skip travel moves
        fig.add_trace(
            go.Scatter3d(
                x=path.xvals,
                y=path.yvals,
                z=path.zvals,
                mode="lines",
                line=dict(width=2, color="dodgerblue"),
                showlegend=False,
                hoverinfo="skip",
            )
        )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="black",
        scene_aspectmode="data",
        scene=dict(
            xaxis=dict(backgroundcolor="black", showgrid=False, visible=False),
            yaxis=dict(backgroundcolor="black", showgrid=False, visible=False),
            zaxis=dict(backgroundcolor="black", showgrid=False, visible=False),
        ),
        width=700,
        height=500,
        margin=dict(l=0, r=0, b=0, t=0),
    )
    return fig
