import streamlit as st


def show_studio_header(
    *,
    project_name,
    project_file,
    is_dirty,
    row_count,
    column_count,
):
    with st.container(
        horizontal=True,
        horizontal_alignment="distribute",
        vertical_alignment="center",
        gap="medium",
        key="studio_header",
    ):
        with st.container(gap="xxsmall"):
            st.caption("Bar chart race editor")
            st.title(project_name or "Untitled project")
            st.caption(
                f"{row_count:,} rows · {column_count:,} columns · {project_file}"
            )

        with st.container(width="content", horizontal_alignment="right"):
            if is_dirty:
                st.badge(
                    "Unsaved changes",
                    icon=":material/edit_note:",
                    color="orange",
                )
            else:
                st.badge(
                    "Saved",
                    icon=":material/cloud_done:",
                    color="green",
                )
            st.badge(
                "Studio workspace",
                icon=":material/animated_images:",
                color="violet",
            )


def show_welcome_header():
    with st.container(key="studio_welcome_header", gap="xsmall"):
        st.caption("Bar chart race editor")
        st.title("BarChartStudio")
        st.caption("Open a project or select a dataset to begin creating.")


def section_intro(title, description, *, icon):
    st.subheader(f":material/{icon}: {title}")
    st.caption(description)


def show_empty_preview():
    with st.container(
        border=True,
        horizontal_alignment="center",
        gap="xsmall",
        key="empty_preview",
    ):
        st.markdown("### :material/visibility: Preview stage")
        st.caption(
            "Choose a year or transition in Export, then select Render preview."
        )
        st.badge(
            "Waiting for preview",
            icon=":material/hourglass_empty:",
            color="gray",
        )


def show_dataset_snapshot(dataset, inspection, *, year_column, name_column):
    period_count = (
        int(dataset[year_column].nunique())
        if year_column in dataset.columns
        else 0
    )
    category_count = (
        int(dataset[name_column].nunique())
        if name_column in dataset.columns
        else 0
    )
    row_metric, period_metric, category_metric = st.columns(3)
    row_metric.metric("Rows", f"{inspection.row_count:,}", border=True)
    period_metric.metric("Periods", f"{period_count:,}", border=True)
    category_metric.metric("Categories", f"{category_count:,}", border=True)
    st.dataframe(dataset.head(10), width="stretch", hide_index=True)
